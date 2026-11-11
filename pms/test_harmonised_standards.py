from datetime import date
from html import escape

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .market_models import HarmonisedStandardReview, MarketAccess, ProductMarket
from .models import AuditLog, Manufacturer, MedicalDevice, Profile


class HarmonisedStandardsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.admin = users.create_superuser("eu-admin")
        cls.reviewer = users.create_user("eu-reviewer")
        Profile.objects.create(user=cls.reviewer, role=Profile.Role.RA_QA)
        cls.scope = MarketAccess.objects.create(user=cls.reviewer, markets=["DE", "US"])
        cls.staff = users.create_user("eu-staff")
        manufacturer = Manufacturer.objects.create(name="Example standards manufacturer")
        cls.device = MedicalDevice.objects.create(name="Example EU device", model_number="EU-TEST", manufacturer=manufacturer)
        cls.us_device = MedicalDevice.objects.create(name="Example US device", model_number="US-TEST", manufacturer=manufacturer)
        ProductMarket.objects.create(device=cls.device, market="DE")
        ProductMarket.objects.create(device=cls.us_device, market="US")

    def setUp(self):
        self.menu = reverse("market-eu-standards")
        self.detail = reverse("market-product-standards", args=[self.device.pk])
        self.data = {
            "regulation": "MDR", "standard_number": "EN EXAMPLE 100", "edition": "Example 2025",
            "eurlex_url": "https://eur-lex.europa.eu/eli/dec_impl/2021/1182/oj",
            "decision_number": "2021/1182", "decision_item": "Example annex item 1",
            "applicability": "hs_applies", "applicability_reason": "Example rationale",
            "review_date": "2026-10-09",
        }

    def test_menu_links_and_language(self):
        self.client.force_login(self.reviewer)
        self.assertContains(self.client.get(reverse("market-dashboard")), self.menu)
        self.assertContains(self.client.get(reverse("market-product", args=[self.device.pk])), self.detail)
        response = self.client.get(self.menu)
        self.assertContains(response, "조화표준")
        self.assertContains(response, self.detail)
        self.assertNotContains(response, self.us_device.name)
        prefix = "https://single-market-economy.ec.europa.eu/single-market/goods/european-standards/"
        for suffix in ("harmonised-standards_en", "harmonised-standards/medical-devices_en",
                       "harmonised-standards/iv-diagnostic-medical-devices_en"):
            self.assertContains(response, f'href="{prefix}{suffix}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"')
        self.client.post(reverse("market-language"), {"language": "en", "next": self.menu})
        self.assertContains(self.client.get(self.menu), "Harmonised standards")
        self.assertContains(self.client.get(self.detail), "Product applicability")

    def test_permissions_and_audit(self):
        self.assertEqual(self.client.get(self.menu).status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.menu).status_code, 403)
        self.assertEqual(self.client.post(self.detail, self.data).status_code, 403)
        self.client.force_login(self.reviewer)
        us_detail = reverse("market-product-standards", args=[self.us_device.pk])
        self.assertEqual(self.client.get(us_detail).status_code, 404)
        self.assertEqual(self.client.post(us_detail, self.data).status_code, 404)
        self.assertRedirects(self.client.post(self.detail, {**self.data, "reviewer": self.admin.pk}), self.detail)
        review = HarmonisedStandardReview.objects.get()
        self.assertEqual((review.reviewer, review.review_date), (self.reviewer, date(2026, 10, 9)))
        self.assertTrue(AuditLog.objects.filter(actor=self.reviewer, action="EU_STANDARD_REVIEW", object_id=str(review.pk)).exists())
        MarketAccess.objects.filter(pk=self.scope.pk).update(markets=["US"])
        self.assertEqual(self.client.get(self.menu).status_code, 404)
        self.assertEqual(self.client.get(self.detail).status_code, 404)
        self.assertEqual(self.client.post(self.detail, self.data).status_code, 404)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("device-detail", args=[self.device.pk])), self.detail)
        self.assertRedirects(self.client.post(self.detail, self.data), self.detail)
        self.assertEqual(HarmonisedStandardReview.objects.first().reviewer, self.admin)

    def test_snapshot_history_and_reference_url_validation(self):
        self.client.force_login(self.reviewer)
        for url in ("https://example.com/eli/dec_impl/2021/1182/oj",
                    self.data["eurlex_url"] + "?patient_id=example", self.data["eurlex_url"] + "#example"):
            with self.subTest(url=url):
                self.assertContains(self.client.post(self.detail, {**self.data, "eurlex_url": url}),
                                    "EUR-Lex 집행결정", status_code=400)
        self.assertFalse(HarmonisedStandardReview.objects.exists())
        self.client.post(self.detail, self.data)
        old = HarmonisedStandardReview.objects.get()
        new_url = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A02021D1182-20250101"
        new = {**self.data, "standard_number": "en  example 100", "edition": "Example 2026",
               "decision_item": "Example annex item 2", "eurlex_url": new_url,
               "applicability": "hs_does_not_apply", "applicability_reason": "Example revised rationale"}
        self.assertRedirects(self.client.post(self.detail, new), self.detail)
        ivdr_data = {**new, "regulation": "IVDR", "decision_number": "2021/1195",
                     "eurlex_url": "https://eur-lex.europa.eu/eli/dec_impl/2021/1195/oj"}
        self.assertRedirects(self.client.post(self.detail, ivdr_data), self.detail)
        response = self.client.get(self.detail)
        ivdr, current, original = response.context["page"].object_list
        self.assertIsNone(ivdr.previous)
        self.assertEqual(current.previous.pk, old.pk)
        self.assertEqual(original.edition, "Example 2025")
        self.assertEqual({field for field, _, _ in current.changes},
                         {"edition", "decision_item", "eurlex_url", "applicability", "applicability_reason"})
        self.assertContains(response, "이전 검토와 비교")
        self.assertContains(response, "Example 2025 → Example 2026")
        self.assertContains(response, f'href="{escape(new_url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"')
        old.edition = "Overwrite"
        with self.assertRaises(ValidationError):
            old.save()
