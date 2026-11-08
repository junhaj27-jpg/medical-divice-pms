"""Project only explicit country evidence; leave all original records untouched."""
from django.db import migrations

# Freeze aliases so migration replay is independent of later catalog edits.
ALIASES = {
    "kr": "KR", "kor": "KR", "한국": "KR", "대한민국": "KR", "south korea": "KR",
    "republic of korea": "KR", "korea (republic of)": "KR",
    "us": "US", "usa": "US", "미국": "US", "united states": "US", "united states of america": "US",
    "de": "DE", "germany": "DE", "deutschland": "DE", "독일": "DE",
    "fr": "FR", "france": "FR", "프랑스": "FR",
    "es": "ES", "spain": "ES", "españa": "ES", "스페인": "ES",
    "it": "IT", "italy": "IT", "italia": "IT", "이탈리아": "IT",
}


def code(value):
    return ALIASES.get((value or "").strip().casefold(), "XX")


def forwards(apps, schema_editor):
    db = schema_editor.connection.alias
    def rows(name):
        return apps.get_model("pms", name).objects.using(db)

    # Use jurisdiction recorded at application time where available; no country
    # inference from UI language, manufacturer location, or an EU-wide record.
    for case in rows("CustomerComplaint").all().iterator(chunk_size=500):
        by_market = {}
        for entry in rows("RuleApplication").filter(complaint_id=case.pk).select_related("rule").order_by("-pk"):
            original = entry.snapshot.get("rule", {})
            jurisdiction = original.get("jurisdiction", entry.snapshot.get("jurisdiction", entry.rule.jurisdiction))
            by_market.setdefault(code(jurisdiction), entry.pk)
        for market, application_id in (by_market or {"XX": None}).items():
            rows("CaseMarket").get_or_create(complaint_id=case.pk, market=market, defaults={
                "legacy_application_id": application_id, "owner_id": case.assignee_id,
                "report_language": "ko-KR",
            })

    status_map = {"APPROVED": "REGISTERED", "APPLICATION": "PREPARATION",
                  "SUPPLEMENT": "IN_REVIEW", "EXPIRED": "EXPIRED"}
    for device in rows("MedicalDevice").all().iterator(chunk_size=500):
        markets = {}
        profiles = rows("RegulatoryProfile").filter(device_id=device.pk)
        for profile in profiles.order_by("pk"):
            markets.setdefault(code(profile.jurisdiction), []).append(profile)
        for market, profiles_in_market in (markets or {"XX": []}).items():
            defaults = {}
            if len(profiles_in_market) == 1 and market != "XX":
                profile = profiles_in_market[0]
                defaults = {"classification": profile.classification, "owner_id": profile.owner_id,
                            "is_example": profile.is_example}
                authorizations = list(rows("MarketingAuthorization").filter(profile_id=profile.pk)[:2])
                if len(authorizations) == 1:
                    record = authorizations[0]
                    defaults.update(pathway=record.kind, identifier=record.number, authority=record.authority,
                                    effective_on=record.issued_on, expires_on=record.expires_on,
                                    status=status_map.get(record.status, "UNKNOWN"))
            rows("ProductMarket").get_or_create(device_id=device.pk, market=market, defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [("pms", "0028_market_workspace")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
