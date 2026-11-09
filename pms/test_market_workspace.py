"""Regression coverage uses fictional products, dates and regulatory rules."""
import importlib
from datetime import date, time, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .market_i18n import label
from .market_models import CaseMarket, MarketAccess, MarketAssessment, MarketEvidence, MarketTranslation, ProductMarket
from .models import AuditLog, CustomerComplaint, MedicalDevice, Profile, RegulatoryReport, ReportingRule, RuleApplication

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], DEBUG=False)
class MarketWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with patch.dict("os.environ", {"DEMO_PASSWORD": "ExampleOnly-A123"}):
            call_command("seed_market_demo", stdout=StringIO())
        cls.hq = get_user_model().objects.get(username="example-hq")
        cls.overseas = get_user_model().objects.get(username="example-overseas")
        cls.case = CustomerComplaint.objects.get(is_example=True)
        cls.device = cls.case.device

    def setUp(self):
        self.client.force_login(self.hq)

    def path(self, name, code=None):
        args = [self.case.pk]
        if code:
            args.append(code)
        return reverse("market-" + name, args=args)

    def entry(self, code):
        return CaseMarket.objects.get(complaint=self.case, market=code)

    def test_language_preference_preserves_market_rule_and_deadline(self):
        before = self.entry("DE").assessments.first()
        row = self.entry("DE")
        destination = self.path("case-country", "DE")
        self.assertContains(self.client.get(destination), "독일")
        response = self.client.post(reverse("market-language"), {"language": "fr-FR", "next": destination}, follow=True)
        self.assertContains(response, '<html lang="fr-FR">')
        self.assertContains(response, "Allemagne")
        self.assertEqual(Profile.objects.get(user=self.hq).ui_language, "fr-FR")
        self.client.post(self.path("evaluate", "DE"))
        after = row.assessments.first()
        self.assertEqual(after.rule_id, before.rule_id)
        self.assertEqual(after.snapshot["calculation"], before.snapshot["calculation"])
        self.assertEqual(after.snapshot["calculation"]["basis_at"], "2026-10-11")
        self.assertEqual(row.report_language, "de-DE")
        self.assertEqual(row.occurred_at_source, "2026-10-10T12:30:00+09:00")

    def test_market_decisions_deadlines_and_reports_are_independent(self):
        us, kr = [self.entry(code) for code in ("US", "KR")]
        self.assertNotEqual(us.assessments.first().snapshot["calculation"]["due_at"],
                            kr.assessments.first().snapshot["calculation"]["due_at"])
        old_case_due = self.case.due_date
        url = self.path("case-country", "US")
        response = self.client.post(url, {"owner": self.overseas.pk, "manual_decision": "NO_REPORT",
                                         "reviewed": "on", "rationale": "Example manual decision"})
        self.assertRedirects(response, url)
        us.refresh_from_db()
        kr.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(us.manual_decision, "NO_REPORT")
        self.assertTrue(us.reviewed)
        self.assertEqual(kr.manual_decision, "HOLD")
        self.assertFalse(kr.reviewed)
        self.assertEqual(self.case.due_date, old_case_due)
        self.assertEqual(ProductMarket.objects.get(device=self.device, market="US").status, "IN_REVIEW")
        self.assertTrue(AuditLog.objects.filter(action="MARKET_CASE", object_id=str(us.pk)).exists())

    def test_eu_sources_are_separate_and_conflict_holds(self):
        de, fr = [self.entry(code) for code in ("DE", "FR")]
        snapshot = de.assessments.first().snapshot
        self.assertEqual({source["scope"] for source in snapshot["evidence"]}, {"EU", "DE"})
        self.assertEqual(fr.assessments.first().snapshot["reason"], "eu_review")
        self.assertContains(self.client.get(self.path("case-country", "DE")), "국가별 추가 요건")
        self.assertContains(self.client.get(self.path("case-country", "DE")), "EU 공동")
        foreign_source = MarketEvidence.objects.get(scope="FR")
        self.assertEqual(self.client.get(reverse("market-case-source", args=[self.case.pk, "DE", foreign_source.pk])).status_code, 404)

    def test_no_approved_rule_and_incomplete_facts_hold(self):
        row = self.entry("US")
        original = row.assessments.first()
        draft = ReportingRule.objects.get(jurisdiction="US", version=2)
        self.assertEqual(draft.state, "DRAFT")
        ReportingRule.objects.filter(pk=original.rule_id).update(state="RETIRED")
        self.client.post(self.path("evaluate", "US"))
        self.assertEqual(row.assessments.first().snapshot["reason"], "no_rule")
        ReportingRule.objects.filter(pk=original.rule_id).update(state="APPROVED", conditions={"serious": False})
        self.client.post(self.path("evaluate", "US"))
        self.assertEqual(row.assessments.first().snapshot["reason"], "missing_input")
        self.assertFalse(row.assessments.first().snapshot.get("calculation"))

    def test_comparison_is_read_only_and_preserves_history(self):
        row = self.entry("KR")
        original = row.assessments.first()
        original_snapshot = original.snapshot.copy()
        draft = ReportingRule.objects.get(jurisdiction="KR", version=2)
        case_values = CustomerComplaint.objects.filter(pk=self.case.pk).values().get()
        count = MarketAssessment.objects.count()
        response = self.client.post(self.path("compare", "KR"), {"baseline": original.rule_id, "proposed": draft.pk})
        self.assertContains(response, "규칙 버전 비교")
        self.assertEqual(response.context["delta"], 1)
        results = response.context["results"]
        self.assertEqual([r["calculation"]["basis_type"] for r in results], ["REPORTED", "OCCURRED"])
        self.assertEqual(MarketAssessment.objects.count(), count)
        self.assertEqual(CustomerComplaint.objects.filter(pk=self.case.pk).values().get(), case_values)
        original.refresh_from_db()
        self.assertEqual(original.snapshot, original_snapshot)
        with self.assertRaises(ValidationError):
            original.save()
        self.client.post(self.path("evaluate", "KR"))
        self.assertEqual(row.assessments.first().snapshot["previous_id"], original.pk)
        self.assertEqual(row.assessments.get(pk=original.pk).snapshot, original_snapshot)

    def test_revised_source_marks_translations_for_review_and_keeps_snapshot(self):
        old = MarketEvidence.objects.get(scope="DE")
        row = self.entry("DE")
        original = row.assessments.first()
        new = MarketEvidence.objects.create(device=self.device, scope="DE", reference_key=old.reference_key,
                                             version=2, title="Beispiel v2", language="de-DE", excerpt="Beispiel",
                                             created_by=self.hq, reviewer=self.hq, checked_on=date(2026, 10, 10),
                                             is_example=True)
        url = reverse("market-case-source", args=[self.case.pk, "DE", old.pk])
        self.assertContains(self.client.get(url), "원문 개정으로 번역 재검토 필요")
        self.assertTrue(MarketTranslation.objects.filter(original=old, reviewed_on__isnull=False).exists())
        self.assertFalse(new.translations.exists())
        self.client.post(self.path("evaluate", "DE"))
        self.assertEqual(row.assessments.first().snapshot["reason"], "eu_review")
        self.assertIn(old.pk, [s["id"] for s in original.snapshot["evidence"]])

    def test_missing_translation_logs_and_uses_english(self):
        with self.assertLogs("pms.i18n", level="WARNING") as output:
            self.assertEqual(label("old_form_help", "it-IT"),
                             "Manage legacy PMS workflow inputs in the original case workspace.")
        self.assertIn("locale=it-IT key=old_form_help", output.output[0])

    def test_market_grants_and_existing_staff_scope_block_direct_access(self):
        self.client.force_login(self.overseas)
        self.assertContains(self.client.get(self.path("case-country", "DE")), "Allemagne")
        self.assertEqual(self.client.get(self.path("case-country", "KR")).status_code, 404)
        self.assertEqual(self.client.get(self.path("report", "KR")).status_code, 404)
        self.assertEqual(self.client.post(self.path("evaluate", "KR")).status_code, 404)
        self.assertEqual(self.client.get(reverse("market-registration", args=[self.device.pk, "KR"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("complaint-workspace", args=[self.case.pk])).status_code, 403)
        self.assertEqual(self.client.get(f"/api/complaints/{self.case.pk}/").status_code, 403)

        private = CustomerComplaint.objects.create(
            device=self.device, udi=self.case.udi, reporter=self.hq, title="Example HQ case",
            description="Example", occurred_on=self.case.occurred_on, complaint_type="EX_SIGNAL",
        )
        CaseMarket.objects.create(complaint=private, market="KR")
        self.assertEqual(self.client.get(reverse("market-case", args=[private.pk])).status_code, 404)
        self.client.logout()
        import base64
        credentials = base64.b64encode(b"example-overseas:ExampleOnly-A123").decode()
        response = self.client.get("/api/complaints/", HTTP_AUTHORIZATION=f"Basic {credentials}")
        self.assertEqual(response.status_code, 403)
        MarketAccess.objects.filter(user=self.overseas).update(markets=[])
        self.client.force_login(self.overseas)
        self.assertEqual(self.client.get(self.path("case-country", "DE")).status_code, 404)
        staff = get_user_model().objects.create_user(username="example-staff")
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.path("case")).status_code, 403)

    def test_all_six_locales_render_dashboard_registration_case_comparison_and_reports(self):
        rule = self.entry("KR").assessments.first().rule
        draft = ReportingRule.objects.get(jurisdiction="KR", version=2)
        report = RegulatoryReport.objects.create(complaint=self.case, author=self.hq, document_number="EX-DEMO")
        for lang, label_text, report_text in (
            ("ko-KR", "해외 인허가", "내부 검토용 보고서 초안"),
            ("en", "Market authorizations", "Draft report for internal review"),
            ("de-DE", "Marktzulassungen", "Berichtsentwurf zur internen Prüfung"),
            ("fr-FR", "Autorisations par marché", "Projet de rapport pour examen interne"),
            ("es-ES", "Autorizaciones por mercado", "Borrador de informe para revisión interna"),
            ("it-IT", "Autorizzazioni per mercato", "Bozza di relazione per verifica interna"),
        ):
            with self.subTest(lang=lang), self.assertNoLogs("pms.i18n", level="WARNING"):
                self.client.post(reverse("market-language"), {"language": lang})
                self.assertContains(self.client.get(reverse("market-dashboard")), label_text)
                for url in (reverse("market-product", args=[self.device.pk]),
                            reverse("market-registration", args=[self.device.pk, "DE"]),
                            self.path("case"), self.path("case-country", "DE")):
                    self.assertContains(self.client.get(url), f'<html lang="{lang}">')
                self.assertContains(self.client.post(self.path("compare", "KR"), {
                    "baseline": rule.pk, "proposed": draft.pk}), f'<html lang="{lang}">')
                self.client.post(self.path("report", "DE"), {"language": lang})
                draft_report = self.client.get(self.path("report", "DE"))
                self.assertContains(draft_report, report_text)
                self.assertEqual(draft_report["Content-Language"], lang)
                self.assertContains(draft_report, "DE scope note")
                self.assertContains(self.client.get(reverse("report-print", args=[report.pk]), {"language": lang}), report_text)
        self.assertEqual(self.entry("DE").report_language, "it-IT")

    def test_backfill_uses_explicit_legacy_jurisdiction_and_preserves_snapshot(self):
        day = date(2026, 10, 10)
        other = CustomerComplaint.objects.create(
            device=self.device, udi=self.case.udi, title="Example older case", description="Example",
            occurred_on=day, reported_on=day, reporter=self.hq, assignee=self.hq, due_date=day + timedelta(days=1),
        )
        unknown = CustomerComplaint.objects.create(
            device=self.device, udi=self.case.udi, title="Example country unknown", description="Example",
            occurred_on=day, reported_on=day, reporter=self.hq,
        )
        kr = ReportingRule.objects.get(jurisdiction="KR", version=1)
        snapshot = {"rule": {"jurisdiction": "대한민국", "version": 1}, "inputs": {"original": "unchanged"}}
        old = RuleApplication.objects.create(complaint=other, rule=kr, actor=self.hq, snapshot=snapshot,
                                             reason="Example legacy", due_at=timezone.now())
        migrate = importlib.import_module("pms.migrations.0029_backfill_market_workspace")
        migrate.forwards(apps, SimpleNamespace(connection=connection))
        row = other.market_cases.get()
        self.assertEqual((row.market, row.legacy_application_id), ("KR", old.pk))
        self.assertEqual(unknown.market_cases.get().market, "XX")
        old.refresh_from_db()
        other.refresh_from_db()
        legacy_url = reverse("market-legacy-snapshot", args=[other.pk, "KR"])
        self.assertContains(self.client.get(legacy_url), "Example legacy")
        self.assertEqual(old.snapshot, snapshot)
        self.assertEqual(other.due_date, day + timedelta(days=1))


    def test_registration_source_and_translation_forms_append_audited_versions(self):
        registration = reverse("market-registration", args=[self.device.pk, "ES"])
        saved = self.client.post(registration, {
            "status": "NA", "na_fields": ["expires_on", "identifier"],
            "is_example": "on", "eu_assessment": "UNKNOWN",
        })
        self.assertRedirects(saved, registration)
        record = ProductMarket.objects.get(device=self.device, market="ES")
        self.assertTrue(record.is_example)
        self.assertEqual(record.na_fields, ["expires_on", "identifier"])
        new_source = reverse("market-evidence-new", args=[self.device.pk, "ES", "ES"])
        data = {"reference_key": "test-scope", "title": "Ejemplo de prueba", "clause": "Ejemplo A",
                "language": "es-ES", "excerpt": "Ejemplo de prueba, no es una obligación legal."}
        for version in (1, 2):
            response = self.client.post(new_source, data)
            source = MarketEvidence.objects.get(scope="ES", reference_key="test-scope", version=version)
            self.assertRedirects(response, reverse("market-evidence", args=[self.device.pk, "ES", source.pk]))
            self.assertTrue(source.is_example)
        translation = reverse("market-translation-new", args=[self.device.pk, "ES", source.pk])
        response = self.client.post(translation, {"language": "it-IT", "text": "Esempio"})
        self.assertRedirects(response, reverse("market-evidence", args=[self.device.pk, "ES", source.pk]))
        self.assertFalse(source.translations.get().reviewed_on)
        self.assertEqual(AuditLog.objects.filter(action="MARKET_EVIDENCE_VERSION").count(), 2)
        self.assertTrue(AuditLog.objects.filter(action="MARKET_TRANSLATION_VERSION").exists())

    def test_example_rule_is_never_used_for_an_operational_case(self):
        operational = CustomerComplaint.objects.create(
            device=self.device, udi=self.case.udi, reporter=self.hq, title="PMS validation case",
            description="Test fixture for example isolation", complaint_type=self.case.complaint_type,
            occurred_on=self.case.occurred_on, reported_on=self.case.reported_on,
        )
        entry = CaseMarket.objects.create(complaint=operational, market="US")
        self.assertEqual(self.client.post(reverse("market-evaluate", args=[operational.pk, "US"])).status_code, 302)
        snapshot = entry.assessments.get().snapshot
        self.assertEqual((snapshot["decision"], snapshot["reason"]), ("HOLD", "no_rule"))
        self.assertEqual(snapshot["evidence"], [])


    def test_rule_interval_uses_case_date_and_deadline_uses_its_own_trigger(self):
        entry = self.entry("US")
        rule_id = entry.assessments.first().rule_id
        ReportingRule.objects.filter(pk=rule_id).update(effective_until=self.case.occurred_on)
        self.client.post(self.path("evaluate", "US"))
        result = entry.assessments.first().snapshot
        self.assertEqual(result["calculation"]["rule_id"], rule_id)
        self.assertEqual(result["calculation"]["basis_at"], self.case.reported_on.isoformat())
