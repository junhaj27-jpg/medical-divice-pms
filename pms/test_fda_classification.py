import io
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .market_models import FDAClassificationEvidence, MarketAccess, ProductMarket
from .models import AuditLog, Manufacturer, MedicalDevice, Profile


class FDAClassificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("classification-ra")
        Profile.objects.create(user=cls.user, role=Profile.Role.RA_QA)
        cls.grant = MarketAccess.objects.create(user=cls.user, markets=["US"])
        manufacturer = Manufacturer.objects.create(name="Classification test manufacturer")
        cls.device = MedicalDevice.objects.create(name="Private product name", model_number="CL-TEST", manufacturer=manufacturer)
        cls.market = ProductMarket.objects.create(device=cls.device, market="US", status="IN_REVIEW", pathway="Pending")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("market-product-fda-classification", args=[self.device.pk])
        self.query = {"search_field": "product_code", "search_term": "nhx", "case_id": "private-data"}

    def mock_response(self):
        return io.BytesIO(json.dumps({"results": [{"product_code": "NHX", "device_name": "Example FDA name",
                                                  "device_class": "2"}]}).encode())

    @patch("pms.fda_classification.urlopen")
    def test_lookup_uses_only_search_fields_and_links_510k(self, fetch):
        fetch.return_value = self.mock_response()
        response = self.client.get(self.url, self.query)
        self.assertContains(response, "Example FDA name")
        self.assertContains(response, "정보 없음")
        requested = urlsplit(fetch.call_args.args[0])
        self.assertEqual(requested.netloc, "api.fda.gov")
        self.assertEqual(parse_qs(requested.query), {"search": ['product_code:"NHX"'], "limit": ["20"]})
        link = reverse("market-product-fda-510k", args=[self.device.pk])
        self.assertContains(response, link + "?product_code=NHX")
        self.assertEqual(self.client.get(link, {"product_code": "NHX"}).context["form"].initial["product_code"], "NHX")
        fetch.return_value = self.mock_response()
        self.client.get(self.url, {"search_field": "device_name", "search_term": "brain monitor"})
        self.assertEqual(parse_qs(urlsplit(fetch.call_args.args[0]).query)["search"], ['device_name:"brain monitor"'])

    @patch("pms.fda_classification.urlopen")
    def test_no_matches_and_failures_are_distinct(self, fetch):
        fetch.side_effect = HTTPError("https://api.fda.gov", 404, "Not found", {},
                                      io.BytesIO(b'{"error":{"code":"NOT_FOUND","message":"No matches found!"}}'))
        self.assertContains(self.client.get(self.url, self.query), "검색 결과가 없습니다.")
        fetch.side_effect = URLError("offline")
        response = self.client.get(self.url, self.query)
        self.assertContains(response, "FDA 조회에 실패했습니다.")
        self.assertContains(response, 'classification.cfm" target="_blank"')

    @patch("pms.fda_classification.urlopen")
    def test_save_duplicate_review_and_market_access(self, fetch):
        fetch.return_value = self.mock_response()
        result, = self.client.get(self.url, self.query).context["results"]
        data = {"action": "save", "snapshot": result["token"]}
        self.assertEqual(self.client.post(self.url, {**data, "snapshot": result["token"] + "bad"}).status_code, 400)
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        evidence = FDAClassificationEvidence.objects.get()
        self.assertTrue(self.client.post(self.url, data).url.endswith(f"#evidence-{evidence.pk}"))
        fetch.return_value = self.mock_response()
        self.assertContains(self.client.get(self.url, self.query), "이미 등록된 근거 보기")
        self.assertEqual(FDAClassificationEvidence.objects.count(), 1)
        self.assertEqual(evidence.snapshot["device_name"], "Example FDA name")
        self.assertIsNotNone(evidence.retrieved_at)
        self.assertIsNone(evidence.reviewed_at)
        self.assertEqual(self.client.post(self.url, {"action": "review", "evidence_id": evidence.pk,
                                                    "review_opinion": "Checked official classification"}).status_code, 302)
        evidence.refresh_from_db()
        self.assertEqual(evidence.reviewer, self.user)
        event = AuditLog.objects.get(action="FDA_CLASSIFICATION_REVIEWED")
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.after["review_opinion"], "Checked official classification")
        self.assertContains(self.client.get(self.url), evidence.review_opinion)
        self.market.refresh_from_db()
        self.assertEqual((self.market.status, self.market.pathway), ("IN_REVIEW", "Pending"))
        MarketAccess.objects.filter(pk=self.grant.pk).update(markets=["DE"])
        fetch.reset_mock()
        self.assertEqual(self.client.get(self.url, self.query).status_code, 404)
        self.assertEqual(self.client.post(self.url, data).status_code, 404)
        fetch.assert_not_called()
