"""German review examples. Uses only fictitious rules, devices and documents."""
from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from pms.market_models import CaseMarket, MarketEvidence, MarketTranslation, ProductMarket
from pms.market_service import assess
from pms.models import CustomerComplaint, Manufacturer, MedicalDevice, ReportingRule, UDI


class Command(BaseCommand):
    help = "Create the fictional German market comparison examples (requires DEMO_PASSWORD)."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_market_demo", stdout=self.stdout)
        users = get_user_model().objects
        hq, approver = (users.get(username=name) for name in ("example-hq", "example-rule-approver"))
        maker, _ = Manufacturer.objects.get_or_create(name="[예시 / Beispiel] MedWatch Review Lab")
        device, _ = MedicalDevice.objects.get_or_create(
            manufacturer=maker, model_number="EX-DE-REVIEW", defaults={"name": "[예시 / Beispiel] DE Review Monitor"},
        )
        udi, _ = UDI.objects.get_or_create(device_identifier="EX-UDI-DE-REVIEW", defaults={"device": device})
        today = timezone.localdate()
        sources = []
        for scope in ("EU", "DE"):
            source, _ = MarketEvidence.objects.get_or_create(
                device=device, scope=scope, reference_key="example-review", version=2 if scope == "DE" else 1,
                defaults={"title": f"[예시 / Beispiel] {scope} Review Reference", "language": "de-DE",
                          "clause": "Beispiel § 2", "excerpt": "Fiktives Material zur internen Demonstration.",
                          "is_example": True, "created_by": hq, "reviewer": approver, "checked_on": today},
            )
            sources.append(source.pk)
            MarketTranslation.objects.get_or_create(
                original=source, language="ko-KR", version=1, defaults={
                    "text": "예시 비교용 가상 문서입니다.", "created_by": hq,
                    "reviewer": approver if scope == "DE" else None,
                    "reviewed_on": today if scope == "DE" else None,
                },
            )
        ProductMarket.objects.get_or_create(device=device, market="DE", defaults={
            "is_example": True, "owner": hq, "status": "IN_REVIEW", "eu_assessment": "ALIGNED",
            "eu_rationale": "Synthetic alignment for the demo", "eu_versions": sorted(sources),
        })
        name = "[예시 / Beispiel] DE vigilance review"
        shared = {"device": device, "jurisdiction": "DE", "is_example": True, "created_by": hq,
                  "conditions": {"complaint_type": "EX_DE_REVIEW"}, "basis": "AWARE",
                  "deadline_unit": "DAYS", "day_type": "BUSINESS", "include_start": False,
                  "deadline_time": time(18), "timezone_name": "Europe/Berlin",
                  "holidays": [{"date": "2026-10-06", "name": "Beispiel-Feiertag"}],
                  "holiday_verified_from": date(2026, 10, 1), "holiday_verified_until": date(2026, 10, 31),
                  "holiday_checked_on": min(today, date(2026, 10, 1))}
        baseline = ReportingRule.objects.filter(name=name, version=1, **{k: shared[k] for k in ("device", "is_example")}).first()
        if not baseline:
            baseline = ReportingRule(name=name, version=1, days=3, effective_on=date(2026, 1, 1),
                                     change_reason="Example baseline", state="APPROVED", approved_by=approver,
                                     approved_at=timezone.now(), **shared)
            baseline._workflow_write = True
            baseline.save()
        ReportingRule.objects.get_or_create(name=name, version=2, device=device, is_example=True, defaults={
            **shared, "days": 1, "effective_on": date(2026, 11, 1), "change_reason": "Example: 3 to 1 business day",
            "family_key": baseline.family_key, "supersedes": baseline,
        })
        for caption, aware in (("Earlier deadline", "2026-10-05"), ("Missing trigger", "")):
            case, _ = CustomerComplaint.objects.get_or_create(
                device=device, title=f"[예시 / Beispiel] {caption}", is_example=True, defaults={
                    "udi": udi, "reporter": hq, "assignee": hq, "complaint_type": "EX_DE_REVIEW",
                    "description": "Fictional complaint for comparison testing.",
                    "occurred_on": date(2026, 10, 5), "reported_on": date(2026, 10, 5),
                },
            )
            entry, _ = CaseMarket.objects.get_or_create(complaint=case, market="DE", defaults={
                "owner": hq, "aware_at_source": aware, "report_language": "de-DE",
            })
            if not entry.assessments.exists():
                assess(entry, hq)
            self.stdout.write(f"CMP-{case.pk} {caption}")
        self.stdout.write(reverse("market-batch-country", args=["DE"]))
