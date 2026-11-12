import io
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .foreign_models import ForeignApplication, ForeignResult
from .market_models import FDA510kReview, MarketAccess, ProductMarket
from .models import AuditLog, BusinessPartner, Manufacturer, MedicalDevice, Profile, RegulatoryProfile
from .ra_services import save_record


class FDA510kTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.admin = users.create_superuser("fda-admin")
        cls.reviewer = users.create_user("fda-reviewer")
        Profile.objects.create(user=cls.reviewer, role=Profile.Role.RA_QA)
        cls.scope = MarketAccess.objects.create(user=cls.reviewer, markets=["US", "DE"])
        cls.staff = users.create_user("fda-staff")
        maker = Manufacturer.objects.create(name="Example FDA manufacturer")
        cls.device = MedicalDevice.objects.create(name="Example US device", model_number="US-TEST", manufacturer=maker)
        cls.other = MedicalDevice.objects.create(name="Example DE device", model_number="DE-TEST", manufacturer=maker)
        cls.market = ProductMarket.objects.create(device=cls.device, market="US", status="IN_REVIEW")
        ProductMarket.objects.create(device=cls.other, market="DE")
        profile = save_record(RegulatoryProfile(), cls.reviewer, dict(
            device=cls.device, jurisdiction="US", organization=BusinessPartner.objects.create(name="Example FDA org"),
            organization_role="MANUFACTURER", title="Example US profile", owner=cls.reviewer, is_example=False,
        ), "Example test setup")
        cls.application = ForeignApplication.objects.create(
            profile=profile, market="US", title="Example 510(k)", kind="NEW", owner=cls.reviewer,
            created_by=cls.reviewer, stage=ForeignApplication.Stage.REVIEW,
        )

    def setUp(self):
        self.menu = reverse("market-us-fda-510k")
        self.detail = reverse("market-product-fda-510k", args=[self.device.pk])
        self.other_detail = reverse("market-product-fda-510k", args=[self.other.pk])
        self.search_url = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm"
        self.data = {
            "purpose": "fda_predicate", "k_number": "k123456", "fda_device_name": "Fictional candidate",
            "applicant_name": "Example applicant", "product_code": "abc", "decision_date": "2024-01-15",
            "fda_decision": "Substantially Equivalent (SE)", "fda_detail_url": self.search_url + "?ID=K123456",
            "review_opinion": "Example internal opinion",
        }

    def test_menu_links_and_locales(self):
        self.client.force_login(self.reviewer)
        self.assertContains(self.client.get(reverse("market-dashboard")), self.menu)
        self.assertContains(self.client.get(reverse("market-product", args=[self.device.pk])), self.detail)
        response = self.client.get(self.menu)
        self.assertContains(response, "FDA 510(k) 공식 검색")
        self.assertContains(response, f'href="{self.search_url}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"')
        self.assertContains(response, self.detail)
        self.assertNotContains(response, self.other.name)
        self.client.post(reverse("market-language"), {"language": "en", "next": self.detail})
        for label in ("FDA source information", "Own product record", "Similar device reference", "Predicate device candidate"):
            self.assertContains(self.client.get(self.detail), label)

    def test_permissions_and_candidate_do_not_change_product_status(self):
        self.assertEqual(self.client.get(self.menu).status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.menu).status_code, 403)
        self.assertEqual(self.client.post(self.detail, self.data).status_code, 403)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(self.other_detail).status_code, 404)
        self.assertEqual(self.client.post(self.other_detail, self.data).status_code, 404)
        market_before, application_before = model_to_dict(self.market), model_to_dict(self.application)
        self.assertRedirects(self.client.post(self.detail, {**self.data, "reviewer": self.admin.pk,
                                                            "reviewed_at": "2000-01-01"}), self.detail)
        entry = FDA510kReview.objects.get()
        self.assertEqual(entry.reviewer, self.reviewer)
        self.assertEqual(timezone.localdate(entry.reviewed_at), timezone.localdate())
        self.assertEqual((entry.k_number, entry.product_code), ("K123456", "ABC"))
        self.assertEqual(entry.fda_decision, self.data["fda_decision"])
        self.assertEqual(entry.review_opinion, self.data["review_opinion"])
        self.market.refresh_from_db()
        self.application.refresh_from_db()
        self.assertEqual(model_to_dict(self.market), market_before)
        self.assertEqual(model_to_dict(self.application), application_before)
        self.assertFalse(ForeignResult.objects.filter(application=self.application).exists())
        self.assertTrue(AuditLog.objects.filter(action="FDA_510K_REVIEW", actor=self.reviewer).exists())
        MarketAccess.objects.filter(pk=self.scope.pk).update(markets=["DE"])
        self.assertEqual(self.client.get(self.menu).status_code, 404)
        self.assertEqual(self.client.get(self.detail).status_code, 404)
        self.assertEqual(self.client.post(self.detail, self.data).status_code, 404)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("device-detail", args=[self.device.pk])), self.detail)
        self.assertRedirects(self.client.post(self.detail, {**self.data, "purpose": "fda_own"}), self.detail)

    def test_snapshots_compare_only_selected_previous_record(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(self.detail, self.data), self.detail)
        old = FDA510kReview.objects.get()
        self.assertRedirects(self.client.post(self.other_detail, self.data), self.other_detail)
        other = FDA510kReview.objects.get(device=self.other)
        self.assertEqual(self.client.post(self.detail, {**self.data, "previous": other.pk}).status_code, 400)
        for url in (self.search_url + "?ID=K654321", self.data["fda_detail_url"] + "&patient=example",
                    self.data["fda_detail_url"].replace("www.accessdata.fda.gov", "example.org")):
            self.assertEqual(self.client.post(self.detail, {**self.data, "fda_detail_url": url}).status_code, 400)
        new_url = "https://www.accessdata.fda.gov/SCRIPTS/cdrh/devicesatfda/index.cfm?db=pmn&id=K654321"
        self.assertRedirects(self.client.post(self.detail, {**self.data, "previous": old.pk, "k_number": "K654321",
                                                           "fda_detail_url": new_url, "review_opinion": "Revised opinion"}), self.detail)
        self.assertRedirects(self.client.post(self.detail, {**self.data, "purpose": "fda_similar"}), self.detail)
        response = self.client.get(self.detail)
        independent, updated, original = response.context["page"].object_list
        self.assertIsNone(independent.previous)
        self.assertEqual(updated.previous_id, old.pk)
        self.assertEqual({field for field, _, _ in updated.changes}, {"k_number", "fda_detail_url", "review_opinion"})
        self.assertContains(response, "K123456 → K654321")
        self.assertContains(response, "Example internal opinion → Revised opinion")
        self.assertContains(response, "FDA 원문 결정 결과")
        self.assertEqual(original.review_opinion, self.data["review_opinion"])
        original.review_opinion = "Overwrite"
        with self.assertRaises(ValidationError):
            original.save()

    @patch("pms.fda_classification.urlopen")
    def test_official_api_selection_and_duplicate(self, fetch):
        self.client.force_login(self.admin)
        product_page = self.client.get(reverse("market-product", args=[self.device.pk]))
        for name in ("market-product-standards", "market-product-fda-classification", "market-product-fda-510k",
                     "market-product-fda-guidance"):
            self.assertContains(product_page, reverse(name, args=[self.device.pk]))
        payload = {"results": [{"k_number": "K123456", "device_name": "Example FDA device", "applicant": "Example applicant",
                                "product_code": "EBZ", "decision_date": "2024-01-15", "decision_description": "Example decision"}]}
        for field, term in (("product_code", "EBZ"), ("k_number", "K123456")):
            fetch.return_value = io.BytesIO(json.dumps(payload).encode())
            response = self.client.get(self.detail, {"search_field": field, "search_term": term, "selected": "K123456"})
            self.assertContains(response, "Example FDA device")
            url = urlsplit(fetch.call_args.args[0])
            self.assertEqual((url.netloc, url.path), ("api.fda.gov", "/device/510k.json"))
            self.assertEqual(parse_qs(url.query), {"search": [f'{field}:"{term}"'], "limit": ["20"]})
        initial = response.context["form"].initial
        data = {**initial, "purpose": "fda_predicate", "review_opinion": "Example review"}
        self.assertRedirects(self.client.post(self.detail, data), self.detail)
        record = FDA510kReview.objects.get()
        self.assertEqual(record.fda_detail_url, initial["fda_detail_url"])
        self.assertContains(self.client.post(self.detail, data, follow=True), "이미 등록된 근거 보기")
        self.assertEqual(FDA510kReview.objects.count(), 1)

        fetch.side_effect = HTTPError("https://api.fda.gov", 404, "Not found", {},
                                      io.BytesIO(b'{"error":{"code":"NOT_FOUND","message":"No matches found!"}}'))
        self.assertContains(self.client.get(self.detail, {"search_field": "product_code", "search_term": "EBZ"}),
                            "검색 결과가 없습니다.")
        fetch.side_effect = URLError("offline")
        error = self.client.get(self.detail, {"search_field": "k_number", "search_term": "K123456"})
        self.assertContains(error, "FDA 조회에 실패했습니다.")
        self.assertContains(error, f'href="{self.search_url}" target="_blank"')
        self.client.force_login(self.staff)
        fetch.reset_mock()
        self.assertEqual(self.client.get(self.detail, {"search_field": "k_number", "search_term": "K123456"}).status_code, 403)
        fetch.assert_not_called()
