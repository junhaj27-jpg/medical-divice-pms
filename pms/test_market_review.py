from codecs import BOM_UTF8
import csv
from datetime import date
from io import StringIO
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .market_models import CaseMarket, MarketAccess, MarketComparisonResult, MarketComparisonRun, MarketEvidence, MarketTranslation
from .models import AuditLog, CustomerComplaint, RegulationChunk, RegulationDocument, ReportingRule, RuleCitation, WorkTask


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

    def test_comparison_csv_matches_filter_and_preserves_codes_across_locales(self):
        self.run_batch()
        run = MarketComparisonRun.objects.get()
        early, missing = run.results.all()
        page = reverse("market-comparison-run", args=[run.pk])
        download = reverse("market-comparison-csv", args=[run.pk])
        response = self.client.get(download)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(response["Content-Disposition"], f'attachment; filename="market-comparison-{run.pk}.csv"')
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(response.content.startswith(BOM_UTF8))
        reader = csv.DictReader(StringIO(response.content.decode("utf-8-sig")))
        first, second = reader
        self.assertEqual(first, {
            "run_id": str(run.pk), "recorded_at": run.recorded_at.isoformat(), "market": "DE",
            "result_id": str(early.pk), "case_id": str(self.early.complaint_id), "is_example": "true",
            "baseline_rule_id": str(self.baseline.pk), "baseline_version": str(self.baseline.version),
            "baseline_decision": early.snapshot["baseline"]["decision"],
            "baseline_basis_date": "2026-10-05", "baseline_due_date": "2026-10-09",
            "proposed_rule_id": str(self.proposed.pk), "proposed_version": str(self.proposed.version),
            "proposed_decision": early.snapshot["proposed"]["decision"],
            "proposed_basis_date": "2026-10-05", "proposed_due_date": "2026-10-07",
            "delta_days": "-2", "changes": "earlier", "review_status": "comparison_pending",
        })
        self.assertEqual(second["result_id"], str(missing.pk))
        self.assertEqual(second["changes"], "review_required")
        for side in ("baseline", "proposed"):
            self.assertEqual(second[f"{side}_decision"], "HOLD")
            self.assertEqual(second[f"{side}_basis_date"], "")
            self.assertEqual(second[f"{side}_due_date"], "")
        self.assertEqual(second["delta_days"], "")
        self.assertContains(self.client.get(page), f'href="{download}"')
        for flag, expected in (("earlier", [first]), ("review_required", [second]), ("later", [])):
            with self.subTest(flag=flag):
                self.assertContains(self.client.get(page, {"change": flag}), f'href="{download}?change={flag}"')
                filtered = self.client.get(download, {"change": flag})
                filtered_reader = csv.DictReader(StringIO(filtered.content.decode("utf-8-sig")))
                self.assertEqual(filtered_reader.fieldnames, reader.fieldnames)
                self.assertEqual(list(filtered_reader), expected)

        for locale, label in (
            ("ko-KR", "CSV 다운로드"), ("en", "Download CSV"), ("de-DE", "CSV herunterladen"),
            ("fr-FR", "Télécharger le CSV"), ("es-ES", "Descargar CSV"), ("it-IT", "Scarica CSV"),
        ):
            with self.subTest(locale=locale):
                self.client.post(reverse("market-language"), {"language": locale, "next": page})
                self.assertContains(self.client.get(page), label)
                self.assertEqual(self.client.get(download).content, response.content)

    def test_comparison_csv_uses_frozen_rule_and_latest_review_without_writes(self):
        self.run_batch()
        run = MarketComparisonRun.objects.get()
        early = run.results.get(entry=self.early)
        download = reverse("market-comparison-csv", args=[run.pk]) + "?change=earlier"

        def exported_row():
            response = self.client.get(download)
            self.assertEqual(response.status_code, 200)
            row, = csv.DictReader(StringIO(response.content.decode("utf-8-sig")))
            return row

        original = exported_row()
        ReportingRule.objects.filter(pk=self.proposed.pk).update(days=8, version=self.proposed.version + 1)
        self.assertEqual(exported_row(), original)
        _, api = self.paths(early)
        state = self.client.get(api).json()
        for complete, expected in ((True, "comparison_complete"), (False, "review_required")):
            state = self.client.post(api, {
                "note": "Private example review note", "complete": complete, "previous": state["revision"],
            }, content_type="application/json").json()
            audit_count = AuditLog.objects.count()
            self.assertEqual(exported_row(), original | {"review_status": expected})
            self.assertEqual(self.client.get(api).json(), state)
            self.assertEqual(AuditLog.objects.count(), audit_count)
        self.assertEqual(self.client.post(download).status_code, 405)

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

    def test_conclusion_follow_up_and_correction_preserve_frozen_evidence(self):
        self.run_batch()
        result = MarketComparisonResult.objects.get(entry=self.early)
        detail, api = self.paths(result)
        task_url = reverse("market-comparison-task", args=[result.pk])
        source = MarketEvidence.objects.get(scope="DE", device_id=self.early.complaint.device_id)
        initial = self.client.get(api).json()
        self.assertEqual(initial["snapshot"]["delta_days"], -2)
        self.assertEqual(self.client.get(task_url).status_code, 404)
        self.assertEqual(self.client.post(api, {"note": "Old note", "complete": False, "previous": 0},
                                         content_type="application/json").status_code, 200)
        self.assertContains(self.client.get(detail), "Old note")
        revision = result.reviews.first().pk
        second_reviewer = Client()
        second_reviewer.force_login(get_user_model().objects.create_superuser(username="second-reviewer"))
        self.assertEqual(second_reviewer.get(api).json()["revision"], revision)
        key = f"market:{source.pk}:ko-KR:1"
        data = {"previous": revision, "conclusion": "follow_up_required", "note": "Review two-day change",
                "complete": "on", "evidence": [key]}
        response = self.client.post(detail, data, follow=True)
        self.assertContains(response, "RA 검토 업무 등록")
        self.assertContains(response, task_url)
        event = result.reviews.first()
        self.assertEqual(event.actor, self.user)
        self.assertIsNotNone(event.recorded_at)
        self.assertEqual(event.evidence, [initial["evidence_options"][key]])
        self.assertEqual((event.evidence[0]["original_version"], event.evidence[0]["version"],
                          event.evidence[0]["language"], event.evidence[0]["clause"]),
                         (2, 1, "ko-KR", "Beispiel § 2"))

        self.assertContains(self.client.get(task_url), "RA 검토 업무 등록")
        task_data = {"assignee": self.user.pk, "title": "Example RA follow-up", "priority": "NORMAL",
                     "due_at": "2026-11-25T10:00", "status": "WAITING"}
        self.assertRedirects(self.client.post(task_url, task_data), task_url)
        task = WorkTask.objects.get(market_comparison=result)
        self.assertEqual(task.complaint_id, self.early.complaint_id)
        self.assertTrue(task.history.exists())
        self.assertContains(self.client.get(detail), "연결된 RA 업무 열기")
        self.assertContains(self.client.get(task_url), task.title)
        self.assertEqual(self.client.get(api).json()["task_id"], task.pk)

        MarketEvidence.objects.create(device=source.device, scope="DE", reference_key=source.reference_key,
                                      version=3, title="New edition", language="de-DE", is_example=True,
                                      created_by=self.user)
        MarketTranslation.objects.create(original=source, language="ko-KR", version=2, text="Revised example",
                                         created_by=self.user)
        stale = second_reviewer.post(detail, {**data, "note": "Stale reviewer"})
        self.assertContains(stale, "최신 기록을 확인", status_code=409)
        self.assertContains(stale, "Review two-day change", status_code=409)
        self.assertEqual(result.reviews.count(), 2)
        correction = {**data, "previous": event.pk, "conclusion": "no_impact", "note": "Scope checked",
                      "complete": True}
        error = self.client.post(api, correction, content_type="application/json")
        self.assertEqual(error.status_code, 400)
        self.assertEqual(error.json()["error"], "comparison_correction_required")
        corrected = self.client.post(api, {**correction, "correction_reason": "Scope clarification"},
                                     content_type="application/json").json()
        self.assertEqual([item["conclusion"] for item in corrected["reviews"]],
                         ["no_impact", "follow_up_required", ""])
        self.assertEqual(corrected["reviews"][1]["evidence"], event.evidence)
        self.assertEqual(corrected["snapshot"], initial["snapshot"])
        self.assertContains(self.client.get(detail), "Scope clarification")
        self.assertContains(self.client.get(detail), "DE Review Reference")
        self.assertNotContains(self.client.get(detail), "New edition")
        self.assertContains(self.client.get(task_url), task.title)
        MarketAccess.objects.create(user=self.user, markets=["KR"])
        for url in (detail, api, task_url):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(api, correction, content_type="application/json").status_code, 404)

    def test_citation_selection_validates_snapshot_and_current_document_permission(self):
        document = RegulationDocument.objects.create(title="Example regulation", edition="v3", jurisdiction="DE",
                                                      uploaded_by=self.peer, is_example=True)
        chunk = RegulationChunk.objects.create(document=document, sequence=1, section="§ 4", paragraph=2)
        citation = RuleCitation.objects.create(rule=self.proposed, chunk=chunk, field_name="days",
                                               quote="Example clause", created_by=self.user)
        self.run_batch()
        result = MarketComparisonResult.objects.get(entry=self.early)
        detail, api = self.paths(result)
        key = f"proposed:{citation.pk}"
        payload = {"previous": 0, "conclusion": "more_evidence_required", "note": "Verify scope",
                   "complete": False, "evidence": ["proposed:999999"]}
        self.assertEqual(self.client.post(api, payload, content_type="application/json").status_code, 400)
        self.assertFalse(result.reviews.exists())
        self.assertContains(self.client.get(detail), "Example regulation")
        saved = self.client.post(api, {**payload, "evidence": [key]}, content_type="application/json").json()
        evidence, = saved["reviews"][0]["evidence"]
        self.assertEqual((evidence["document_id"], evidence["version"], evidence["clause"]),
                         (document.pk, "v3", "§ 4 / 2"))
        # Simulate a revoked TEAM grant without using the production document editor.
        RegulationDocument.objects.filter(pk=document.pk).update(visibility="PRIVATE")
        for url in (detail, api):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(api, payload, content_type="application/json").status_code, 404)

    def test_saved_comparison_api_and_screen_enforce_market_and_author_access(self):
        self.run_batch()
        result = MarketComparisonResult.objects.get(entry=self.early)
        detail, api = self.paths(result)
        download = reverse("market-comparison-csv", args=[result.run_id])
        self.assertEqual(self.client.get(download).status_code, 200)
        self.client.force_login(self.peer)
        self.assertEqual(self.client.get(download).status_code, 404)
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.assertEqual(self.client.get(api).status_code, 404)
        self.client.force_login(self.user)
        data = json.dumps({"note": "Example review", "complete": True, "previous": 0})
        self.assertEqual(self.client.post(api, data, content_type="application/json").json()["review_status"], "comparison_complete")
        MarketAccess.objects.create(user=self.user, markets=["KR"])
        self.assertEqual(self.client.get(download).status_code, 404)
        self.assertEqual(self.client.get(api).status_code, 404)
        self.assertEqual(self.client.post(api, data, content_type="application/json").status_code, 404)
        self.assertEqual(self.client.get(detail).status_code, 404)
