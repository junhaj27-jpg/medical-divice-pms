"""Create only synthetic records; no regulatory text, real source URL or real deadline."""
import os
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from pms.market_models import CaseMarket, MarketAccess, MarketEvidence, MarketTranslation, ProductMarket
from pms.market_service import assess
from pms.models import CustomerComplaint, Manufacturer, MedicalDevice, Profile, ReportingRule, UDI
from pms.services import audit


class Command(BaseCommand):
    help = "Seed the isolated four-market example (requires DEMO_PASSWORD)."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv("DEMO_PASSWORD", "")
        if len(password) < 8:
            raise CommandError("Set DEMO_PASSWORD (at least 8 characters) in an isolated local database.")
        users = {}
        for name, markets, lang, role in (
            ("example-hq", None, "ko-KR", "RA_QA"), ("example-overseas", ["US", "DE", "FR"], "fr-FR", "RA_QA"),
            ("example-rule-approver", None, "en", "ADMIN"),
        ):
            user, created = get_user_model().objects.get_or_create(username=name)
            if created:
                if role == "ADMIN":
                    user.set_unusable_password()
                else:
                    user.set_password(password)
                user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            if created:
                profile.role, profile.ui_language = role, lang
                profile.save()
                if markets is not None:
                    MarketAccess.objects.create(user=user, markets=markets)
            users[name] = user
        hq, reviewer = users["example-hq"], users["example-rule-approver"]
        maker, _ = Manufacturer.objects.get_or_create(name="[예시 / Example] Northstar Instruments")
        device, _ = MedicalDevice.objects.get_or_create(
            manufacturer=maker, model_number="EX-PULSE-1", defaults={"name": "[예시 / Example] Pulse Monitor"},
        )
        udi, _ = UDI.objects.get_or_create(device_identifier="EX-UDI-PULSE-1", defaults={"device": device})
        case, _ = CustomerComplaint.objects.get_or_create(
            device=device, title="[예시 / Example] Intermittent signal loss", is_example=True, defaults={
                "udi": udi, "reporter": hq, "assignee": hq, "complaint_type": "EX_SIGNAL",
                "description": "Synthetic case: the test monitor intermittently lost its signal.",
                "occurred_on": date(2026, 10, 10), "reported_on": date(2026, 10, 11),
            },
        )
        today = timezone.localdate()
        sources = {}
        for scope, lang, excerpt in (
            ("EU", "en", "Example: shared evidence for the simulated product family."),
            ("KR", "ko-KR", "예시: 시험 제품의 한국 시장 검토 메모입니다."),
            ("US", "en", "Example: national submission scope is still under internal review."),
            ("DE", "de-DE", "Beispiel: Nationale Ergänzung für das Testprodukt."),
            ("FR", "fr-FR", "Exemple : exigence nationale fictive à clarifier."),
        ):
            source, _ = MarketEvidence.objects.get_or_create(
                device=device, scope=scope, reference_key="example-scope", version=1,
                defaults={"title": f"[예시 / Example] {scope} scope note", "clause": "Example § A",
                          "language": lang, "excerpt": excerpt, "checked_on": today, "reviewer": hq,
                          "created_by": hq, "is_example": True},
            )
            sources[scope] = source
            for code, text in (
                ("ko-KR", "예시: 실제 인허가나 보고 요건이 아닌 내부 시연 자료입니다."),
                ("en", "Example: this is an internal simulation and states no actual regulatory requirement."),
                ("de-DE", "Beispiel: Diese interne Simulation enthält keine tatsächliche regulatorische Anforderung."),
                ("fr-FR", "Exemple : cette simulation interne ne contient aucune obligation réglementaire réelle."),
            ):
                if code != lang:
                    MarketTranslation.objects.get_or_create(original=source, language=code, version=1, defaults={
                        "text": text, "created_by": hq, "reviewer": None if scope == "FR" else reviewer,
                        "reviewed_on": None if scope == "FR" else today,
                    })

        for market, lang, zone, status, days in (
            ("KR", "ko-KR", "Asia/Seoul", "REGISTERED", 3),
            ("US", "en", "America/New_York", "IN_REVIEW", 7),
            ("DE", "de-DE", "Europe/Berlin", "PREPARATION", 5),
            ("FR", "fr-FR", "Europe/Paris", "UNKNOWN", None),
        ):
            owner = hq if market == "KR" else users["example-overseas"]
            ProductMarket.objects.get_or_create(device=device, market=market, defaults={
                "is_example": True, "owner": owner, "status": status,
                "identifier": "EX-REG-KR" if market == "KR" else "", "pathway": "Example pathway",
                "classification": "Example class", "submission_language": lang,
                "effective_on": today - timedelta(days=90) if market == "KR" else None,
                "expires_on": today + timedelta(days=45) if market == "KR" else None,
                "submissions": "Example scope note and simulated checklist",
                "authority": "Example internal review team", "rationale": "Synthetic portfolio data",
                "eu_assessment": "ALIGNED" if market == "DE" else "CONFLICT" if market == "FR" else "UNKNOWN",
                "eu_rationale": "Example scope reconciliation" if market in ("DE", "FR") else "",
                "eu_versions": sorted((sources["EU"].pk, sources[market].pk)) if market in ("DE", "FR") else [],
            })
            entry, _ = CaseMarket.objects.get_or_create(complaint=case, market=market, defaults={
                "owner": owner, "report_language": lang, "occurred_at_source": "2026-10-10T12:30:00+09:00",
            })
            if days:
                name = f"[예시 / Example] {market} synthetic signal rule"
                rule = ReportingRule.objects.filter(name=name, version=1, is_example=True, device=device).first()
                if not rule:
                    rule = ReportingRule(
                        name=name, jurisdiction=market, device=device, is_example=True, created_by=hq,
                        conditions={"complaint_type": "EX_SIGNAL"}, effective_on=date(2026, 1, 1),
                        basis="REPORTED", days=days, day_type="CALENDAR", include_start=False,
                        deadline_unit="DAYS", deadline_time=time(18), timezone_name=zone,
                        change_reason="Example only; generated by seed_market_demo",
                        scope_description="Example test device only", state="APPROVED",
                        approved_by=reviewer, reviewed_by=reviewer, approved_at=timezone.now(),
                    )
                    rule._workflow_write = True  # Synthetic fixture only; real approval uses regulatory.transition_rule.
                    rule.save()
                    audit(hq, "MARKET_DEMO_RULE", rule, after={"market": market, "example": True})
                if not ReportingRule.objects.filter(family_key=rule.family_key, version=2).exists():
                    ReportingRule.objects.create(
                        name=name, family_key=rule.family_key, version=2, supersedes=rule, device=device,
                        jurisdiction=market, is_example=True, created_by=owner, conditions=rule.conditions,
                        effective_on=date(2026, 11, 1), basis="OCCURRED", days=days + 2, day_type="CALENDAR",
                        include_start=False, deadline_unit="DAYS", deadline_time=time(18), timezone_name=zone,
                        change_reason="Example draft: change trigger and illustrative days",
                    )
            if not entry.assessments.exists():
                assess(entry, hq)

        self.stdout.write("Example logins: example-hq / example-overseas")
        self.stdout.write(reverse("market-dashboard"))
        self.stdout.write(reverse("market-product", args=[device.pk]))
        self.stdout.write(reverse("market-case", args=[case.pk]))
