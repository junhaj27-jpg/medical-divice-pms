from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from .market_models import GuidanceApplicabilityReview, MarketAccess, MarketEvidence, ProductMarket
from .models import AuditLog, Manufacturer, MedicalDevice, Profile


class FDAGuidanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ra = get_user_model().objects.create_user("guidance-ra")
        Profile.objects.create(user=cls.ra, role=Profile.Role.RA_QA)
        cls.grant = MarketAccess.objects.create(user=cls.ra, markets=["US"])
        maker = Manufacturer.objects.create(name="Example dental manufacturer")
        cls.device = MedicalDevice.objects.create(name="Example curing light", model_number="DCL-EX", manufacturer=maker)
        cls.market = ProductMarket.objects.create(device=cls.device, market="US", status="IN_REVIEW", pathway="Pending")

    def setUp(self):
        self.client.force_login(self.ra)
        self.url = reverse("market-product-fda-guidance", args=[self.device.pk])

    def test_open_link_and_review_without_changing_market_status(self):
        registration = reverse("market-registration", args=[self.device.pk, "US"])
        self.assertContains(self.client.get(registration), self.url)
        page = self.client.get(self.url)
        self.assertContains(page, "Dental Curing Lights")
        self.assertContains(page, "2026-09-02")
        self.assertContains(page, "최종본")
        self.assertContains(page, 'dental-curing-lights-premarket-notification-510k-submissions" target="_blank"')
        self.assertContains(page, 'https://www.fda.gov/media/74206/download" target="_blank"')
        self.assertContains(self.client.post(self.url, {"action": "link"}, follow=True), "검토 대기")
        self.assertRedirects(self.client.post(self.url, {"action": "link"}), self.url)
        source = MarketEvidence.objects.get()
        self.assertEqual(source.document_type, "FDA_GUIDANCE")
        self.assertEqual(source.document_metadata["issued_on"], "2026-09-02")
        self.assertIsNotNone(source.checked_on)
        self.assertContains(self.client.get(registration), source.title)
        self.assertEqual(AuditLog.objects.filter(action="FDA_GUIDANCE_LINKED").count(), 1)

        rationale = "Example review of the product's intended use"
        response = self.client.post(self.url, {"action": "review", "applicability": "hs_applies",
                                              "applicability_reason": rationale}, follow=True)
        self.assertContains(response, escape(rationale))
        event = GuidanceApplicabilityReview.objects.get(evidence=source)
        self.assertEqual((event.reviewer, event.decision), (self.ra, "hs_applies"))
        audit = AuditLog.objects.get(action="FDA_GUIDANCE_REVIEWED")
        self.assertEqual((audit.actor, audit.after["reviewed_at"], audit.after["rationale"]),
                         (self.ra, event.reviewed_at.isoformat(), rationale))
        self.market.refresh_from_db()
        self.assertEqual((self.market.status, self.market.pathway), ("IN_REVIEW", "Pending"))

    @patch("pms.fda_classification.lookup")
    def test_candidate_links_use_ebz_and_access_is_rechecked(self, lookup):
        classification = reverse("market-product-fda-classification", args=[self.device.pk])
        cases = reverse("market-product-fda-510k", args=[self.device.pk])
        for code in ("EBZ", "QNF", "EEG"):
            with self.subTest(code=code):
                lookup.return_value = [{"product_code": code, "device_name": "Example", "device_class": "2",
                                        "regulation_number": "872.6070"}]
                lookup_page = self.client.get(classification, {"search_field": "product_code", "search_term": code})
                case_page = self.client.get(cases, {"product_code": code})
                for response in (lookup_page, case_page):
                    if code == "EBZ":
                        self.assertContains(response, self.url)
                    else:
                        self.assertNotContains(response, self.url)
        self.assertFalse(MarketEvidence.objects.exists())
        self.client.post(self.url, {"action": "link"})
        MarketAccess.objects.filter(pk=self.grant.pk).update(markets=["DE"])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"action": "link"}).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"action": "review", "applicability": "hs_applies",
                                                    "applicability_reason": "Unauthorized"}).status_code, 404)
        self.assertFalse(GuidanceApplicabilityReview.objects.exists())
