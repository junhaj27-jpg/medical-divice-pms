from datetime import date
from io import StringIO
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .market_models import CaseMarket, MarketAccess, MarketComparisonResult, MarketComparisonRun, MarketEvidence, MarketTranslation
from .models import AuditLog, CustomerComplaint, ReportingRule


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], DEBUG=False)
class MarketReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with patch.dict("os.environ", {"DEMO_PASSWORD": "Synthetic-Only-2026!"}):
            call_command("seed_market_review_demo", stdout=StringIO())
        cls.user = get_user_model().objects.get(username="example-hq")
        cls.peer = get_user_model().objects.get(username="example-overseas")
        cls.early, cls.missing = CaseMarket.objects.filter(
            market="DE", complaint__device__model_number="EX-DE-REVIEW",
        ).order_by("pk")
        cls.baseline, cls.proposed = ReportingRule.objects.filter(
            jurisdiction="DE", device__model_number="EX-DE-REVIEW",
        ).order_by("version")
        cls.batch_url = reverse("market-batch-country", args=["DE"])

    def setUp(self):
        self.client.force_login(self.user)

    def run_batch(self):
        return self.client.post(self.batch_url, {"baseline": self.baseline.pk, "proposed": self.proposed.pk,
                                                "case": [self.early.complaint_id, self.missing.complaint_id]}, follow=True)

    def paths(self, result):
        return [reverse("market-comparison-result", args=[result.pk]),
                reverse("market-comparison-api", args=[result.pk])]

    def test_de_filter_review_reopen_and_operating_snapshot_is_unchanged(self):
        operational = self.early.assessments.first()
        assessment_url = reverse("market-operating-snapshot", args=[self.early.complaint_id, "DE", operational.pk])
        before = self.client.get(assessment_url)
        complaint = CustomerComplaint.objects.values().get(pk=self.early.complaint_id)
        with patch("pms.market_batch.native_engine", return_value=None):
            response = self.run_batch()
        self.assertContains(response, "기한 앞당김")
        run = MarketComparisonRun.objects.get()
        early, missing = run.results.all()
        self.assertEqual(early.snapshot["delta_days"], -2)
        self.assertEqual(early.snapshot["baseline"]["due_date"], "2026-10-09")
        self.assertEqual(early.snapshot["proposed"]["due_date"], "2026-10-07")
        self.assertEqual(missing.snapshot["explanations"]["baseline"]["input_issue"], "missing_basis_date")
        self.assertIsNone(missing.snapshot["delta_days"])
        for flag, expected in (("earlier", early), ("review_required", missing)):
            filtered = self.client.get(reverse("market-comparison-run", args=[run.pk]), {"change": flag})
            self.assertEqual([r["result_id"] for r in filtered.context["rows"]], [expected.pk])
        detail, api = self.paths(early)
        self.assertContains(self.client.get(detail), "DE Review Reference")
        snapshot = self.client.get(api).json()["snapshot"]
        self.client.post(reverse("market-language"), {"language": "de-DE", "next": detail})
        self.assertContains(self.client.get(detail), "Vergleichsdetails")
        self.assertEqual(self.client.get(api).json()["snapshot"], snapshot)
        reselection = self.client.get(self.batch_url, {"run": run.pk})
        self.assertEqual(reselection.context["selected"], [str(self.early.complaint_id), str(self.missing.complaint_id)])
        self.assertEqual(reselection.context["baseline_id"], str(self.baseline.pk))
        note = "Nur synthetische Prüfdaten"
        self.assertContains(self.client.post(detail, {"note": note, "complete": "on", "previous": 0}, follow=True), note)
        history = reverse("market-comparison-history", args=[self.early.complaint_id, "DE"])
        self.assertContains(self.client.get(history), detail)
        self.assertEqual(self.client.get(api).json()["review_status"], "comparison_complete")
        self.assertEqual(self.client.post(detail, {"note": "stale", "previous": 0}).status_code, 409)
        log = AuditLog.objects.get(action="MARKET_COMPARISON_REVIEW")
        self.assertNotIn(note, str(log.after))
        operational.refresh_from_db()
        self.assertEqual(self.client.get(assessment_url).context["record"].snapshot, before.context["record"].snapshot)
        self.assertEqual(CustomerComplaint.objects.values().get(pk=self.early.complaint_id), complaint)
        self.baseline.refresh_from_db()
        self.proposed.refresh_from_db()
        self.assertEqual((self.baseline.state, self.proposed.state), ("APPROVED", "DRAFT"))

    def test_historical_rules_and_translation_versions_are_frozen(self):
        self.run_batch()
        saved = MarketComparisonResult.objects.get(entry=self.early)
        api = self.paths(saved)[1]
        before = self.client.get(api).json()
        ReportingRule.objects.filter(pk=self.proposed.pk).update(days=8)
        source = MarketEvidence.objects.get(scope="DE", device_id=self.early.complaint.device_id)
        MarketTranslation.objects.create(original=source, language="ko-KR", version=2,
                                         text="Fictional revision", created_by=self.user)
        after = self.client.get(api).json()
        self.assertEqual(after["rules"]["proposed"]["days"], 1)
        self.assertEqual(before["snapshot"], after["snapshot"])
        self.assertEqual([s for s in after["snapshot"]["sources"] if s["scope"] == "DE"][0]["translations"][0]["version"], 1)

    def test_missing_baseline_and_required_facts_have_distinct_reasons(self):
        ReportingRule.objects.filter(pk=self.baseline.pk).update(effective_on=date(2026, 11, 1))
        ReportingRule.objects.filter(pk=self.proposed.pk).update(conditions={"serious": True})
        response = self.run_batch()
        self.assertContains(response, "이 사건에 적용할 승인 기준본 확인 필요")
        result = MarketComparisonResult.objects.get(entry=self.early)
        self.assertEqual(result.snapshot["baseline"]["reason"], "baseline_unavailable")
        self.assertEqual(result.snapshot["explanations"]["proposed"]["input_issue"], "missing_facts")
        self.assertEqual(result.snapshot["explanations"]["proposed"]["conditions"][0]["status"], "condition_unknown")
        ReportingRule.objects.filter(pk=self.baseline.pk).update(state="DRAFT")
        self.assertContains(self.run_batch(), "이 시장의 이전 승인본을 특정할 수 없습니다", status_code=400)

    def test_saved_comparison_api_and_screen_enforce_market_and_author_access(self):
        self.run_batch()
        result = MarketComparisonResult.objects.get(entry=self.early)
        detail, api = self.paths(result)
        self.client.force_login(self.peer)
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.assertEqual(self.client.get(api).status_code, 404)
        self.client.force_login(self.user)
        data = json.dumps({"note": "Example review", "complete": True, "previous": 0})
        self.assertEqual(self.client.post(api, data, content_type="application/json").json()["review_status"], "comparison_complete")
        MarketAccess.objects.create(user=self.user, markets=["KR"])
        self.assertEqual(self.client.get(api).status_code, 404)
        self.assertEqual(self.client.post(api, data, content_type="application/json").status_code, 404)
        self.assertEqual(self.client.get(detail).status_code, 404)
