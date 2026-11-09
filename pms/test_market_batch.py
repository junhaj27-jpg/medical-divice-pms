import importlib.util
from datetime import date, time
from io import StringIO
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .market_batch import native_engine, run
from .market_models import CaseMarket, MarketAssessment
from .models import Approval, AuditLog, CustomerComplaint, ReportingRule, RuleApplication, WorkTask


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], DEBUG=False)
class MarketBatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with patch.dict("os.environ", {"DEMO_PASSWORD": "ExampleOnly-B123"}):
            call_command("seed_market_demo", stdout=StringIO())
        cls.hq = get_user_model().objects.get(username="example-hq")
        cls.overseas = get_user_model().objects.get(username="example-overseas")
        cls.case = CustomerComplaint.objects.get(is_example=True)
        cls.kr = list(ReportingRule.objects.filter(jurisdiction="KR").order_by("version"))

    def setUp(self):
        self.client.force_login(self.hq)
        self.url = reverse("market-batch-country", args=["KR"])
        self.data = {"baseline": self.kr[0].pk, "proposed": self.kr[1].pk, "case": [self.case.pk]}

    def test_python_fallback_and_no_operational_writes(self):
        models = (CustomerComplaint, CaseMarket, MarketAssessment, ReportingRule, RuleApplication, Approval, WorkTask)
        def state():
            return [list(model.objects.order_by("pk").values()) for model in models]
        before = state()
        with patch("pms.market_batch.native_engine", return_value=None):
            response = self.client.post(self.url, self.data, follow=True)
        self.assertContains(response, "C++ 모듈 미설치 또는 로드 불가")
        row, = response.context["rows"]
        self.assertEqual(row["changes"], ["later"])
        self.assertEqual(row["delta_days"], 1)
        self.assertEqual(state(), before)
        log = AuditLog.objects.get(action="MARKET_RULE_BATCH")
        self.assertEqual(log.actor, self.hq)
        self.assertEqual(log.after["market"], "KR")
        self.assertEqual(log.after["engines"], ["python"])
        self.assertEqual(log.after["count"], 1)
        self.assertNotIn(self.case.description, str(log.after))

    def test_forbidden_market_rule_and_case_are_rejected(self):
        self.client.force_login(self.overseas)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.data, follow=True).status_code, 404)
        self.client.force_login(self.hq)
        other = ReportingRule.objects.filter(jurisdiction="US").first()
        self.assertEqual(self.client.post(self.url, {**self.data, "proposed": other.pk}).status_code, 400)
        private = CustomerComplaint.objects.create(
            device=self.case.device, udi=self.case.udi, reporter=self.hq, title="Example other market",
            description="Example", occurred_on=self.case.occurred_on, complaint_type="EX_SIGNAL",
        )
        CaseMarket.objects.create(complaint=private, market="US")
        self.assertEqual(self.client.post(self.url, {**self.data, "case": [private.pk]}).status_code, 400)
        staff = get_user_model().objects.create_user(username="batch-staff")
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_limits_and_entry_points(self):
        self.assertContains(self.client.get(reverse("market-dashboard")), reverse("market-batch"))
        compare = reverse("market-compare", args=[self.case.pk, "KR"])
        self.assertContains(self.client.get(compare), self.url)
        self.assertEqual(self.client.post(self.url, {**self.data, "case": []}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {**self.data, "case": list(range(1, 102))}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {**self.data, "case": [self.case.pk] * 2}).status_code, 400)

    def test_mismatch_names_fields_and_keeps_python_value(self):
        entry = CaseMarket.objects.get(complaint=self.case, market="KR")
        with patch("pms.market_batch.native_engine", return_value=None):
            expected, = run([entry], self.kr, self.hq, "KR")

        native = native_engine()

        def inconsistent(text):
            request = json.loads(text)
            self.assertEqual(request["cases"][0]["id"], str(self.case.pk))
            if native:
                payload = json.loads(native(text))
            else:
                row = {key: expected[key] for key in ("case_id", "baseline", "proposed", "changes", "delta_days")}
                payload = {"schema_version": 1, "market": "KR", "results": [row]}
            payload["results"][0]["baseline"]["due_date"] = "2040-01-01"
            return json.dumps(payload)

        with patch("pms.market_batch.native_engine", return_value=inconsistent):
            response = self.client.post(self.url, self.data, follow=True)
        self.assertContains(response, "검토 필요")
        row, = response.context["rows"]
        self.assertEqual(row["mismatches"][0]["field"], "due_date")
        self.assertEqual(row["baseline"]["due_date"], expected["baseline"]["due_date"])
        detail = reverse("market-comparison-result", args=[row["result_id"]])
        self.assertContains(self.client.get(detail), "2040-01-01")

    def test_actual_binding_supported_case_and_offset_fallback(self):
        if importlib.util.find_spec("pms_rule_batch") is None:
            self.skipTest("optional pybind11 module is not on PYTHONPATH")
        CaseMarket.objects.filter(complaint=self.case, market="KR").update(occurred_at_source="")
        response = self.client.post(self.url, self.data, follow=True)
        row, = response.context["rows"]
        self.assertFalse(row["mismatches"])
        self.assertEqual({v["name"] for v in row["engines"].values()}, {"cpp_verified"})
        # Recorded local date is March 1. The UTC calculation begins on February 29.
        ReportingRule.objects.filter(pk=self.kr[0].pk).update(timezone_name="UTC", deadline_time=time(18), days=1)
        CustomerComplaint.objects.filter(pk=self.case.pk).update(reported_on=date(2024, 3, 1))
        CaseMarket.objects.filter(complaint=self.case, market="KR").update(
            reported_at_source="2024-03-01T00:30:00+09:00",
        )
        row, = self.client.post(self.url, self.data, follow=True).context["rows"]
        self.assertEqual(row["baseline"]["basis_date"], "2024-02-29")
        self.assertEqual(row["baseline"]["due_at"], "2024-03-01T18:00:00+00:00")
        self.assertEqual(row["engines"]["baseline"], {"name": "python", "fallback": "unsupported_timestamp"})

    def test_six_locales_render_same_result_and_dates(self):
        with patch("pms.market_batch.native_engine", return_value=None):
            initial = self.client.post(self.url, self.data, follow=True)
        run_url = initial.redirect_chain[-1][0]
        expected = initial.context["rows"]
        for locale in ("ko-KR", "en", "de-DE", "fr-FR", "es-ES", "it-IT"):
            self.client.post(reverse("market-language"), {"language": locale, "next": run_url})
            with self.subTest(locale=locale), self.assertNoLogs("pms.i18n", level="WARNING"):
                response = self.client.get(run_url)
                self.assertContains(response, f'<html lang="{locale}">')
                self.assertEqual(response.context["rows"], expected)
