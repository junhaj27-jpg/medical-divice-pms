"""Market access and reproducible, read-only evaluation of existing rule versions."""
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfoNotFoundError

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .market_codes import market_code
from .market_models import (
    COUNTRIES, EU_COUNTRIES, CaseMarket, MarketAssessment, MarketEvidence, ProductMarket,
)
from .models import CustomerComplaint, MedicalDevice, RuleFamilyLock
from .regulatory import calculate_deadline, readiness, rule_payload, rules_for
from .rule_comparison import deadline_delta
from .services import audit, role, visible_complaints

BASIS_FIELDS = {
    "OCCURRED": ("occurred_at_source", "occurred_on"),
    "REPORTED": ("reported_at_source", "reported_on"),
    "AWARE": ("aware_at_source", None),
    "CUSTOM": ("custom_at_source", None),
}


def scoped(user):
    return user.is_authenticated and role(user) != "ADMIN" and hasattr(user, "market_access")


def allowed_markets(user):
    if not user.is_authenticated or not user.is_active or role(user) not in ("RA_QA", "ADMIN"):
        return ()
    if scoped(user):
        return tuple(code for code in COUNTRIES if code in user.market_access.markets)
    return (*COUNTRIES, "XX")


def require_workspace(user):
    if not user.is_authenticated or not user.is_active or role(user) not in ("RA_QA", "ADMIN"):
        raise PermissionDenied


def case_markets(user):
    return CaseMarket.objects.filter(
        market__in=allowed_markets(user), complaint__in=visible_complaints(user)
    ).select_related("complaint__device", "owner", "legacy_application__rule")


def product_markets(user):
    return ProductMarket.objects.filter(market__in=allowed_markets(user)).select_related("device", "owner")


def source_scopes(market):
    return (market, "EU") if market in EU_COUNTRIES else (market,)


def evidence_for(case):
    """Current version per evidence key; keep previous versions available for comparison."""
    entries = MarketEvidence.objects.filter(
        device_id=case.complaint.device_id, scope__in=source_scopes(case.market),
        is_example=case.complaint.is_example,
    ).select_related("reviewer").prefetch_related("translations__reviewer")
    return evidence_versions(entries)


def evidence_versions(entries):
    groups = {}
    for source in entries.order_by("scope", "reference_key", "-version"):
        groups.setdefault((source.scope, source.reference_key), []).append(source)
    return [(versions[0], versions[1:]) for versions in groups.values()]


def source_record(source):
    return {
        "id": source.pk, "title": source.title, "version": source.version, "clause": source.clause,
        "scope": source.scope, "language": source.language, "url": source.official_url,
        "document_id": source.regulation_document_id,
        "checked_on": str(source.checked_on or ""), "reviewer": str(source.reviewer or ""),
        "translations": [
            {"language": t.language, "version": t.version, "reviewed": bool(t.reviewed_on and t.reviewer_id)}
            for t in source.translations.all().order_by("language", "-version")
        ],
    }


def parse_source(value):
    """Accept an exact business date or a timestamp with an explicit offset."""
    if len(value) == 10:
        return date.fromisoformat(value)
    if "T" not in value:
        raise ValueError("Expected ISO date or offset timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("Expected explicit UTC offset")
    return stamp


def hold(code, rule=None, **data):
    return {"decision": "HOLD", "reason": code, "rule": rule, **data}


def version_result(rule, entry, user, *, preview=False):
    """Use the original PMS deadline engine; avoid treating unknown facts as false."""
    c = entry.complaint
    if market_code(rule.jurisdiction) != entry.market or (rule.device_id and rule.device_id != c.device_id):
        return hold("scope_mismatch")
    if rule.is_example != c.is_example:
        return hold("scope_mismatch")
    if not preview and not rule.is_example and readiness(rule, user):
        return hold("source_unverified")
    payload = rule_payload(rule)
    if not preview and not rule.is_example:
        approval = rule.changes.filter(action="RULE_APPROVE", actor_id=rule.approved_by_id).order_by("-pk").first()
        if not approval or any(approval.after.get(k) != value for k, value in payload.items()):
            return hold("source_unverified")
    if preview:
        # Draft citations may include private originals; use the existing visibility check.
        from .regulation_documents import documents_for
        visible = set(documents_for(user).values_list("pk", flat=True))
        if any(s["document_id"] not in visible for s in payload["citations"]):
            return hold("source_unverified")
    data = {"rule": payload}
    if rule.unresolved_items or (not rule.is_example and (
        not payload["citations"] or any(not source["official_url"].startswith("https://") for source in payload["citations"])
        or rule.citations.filter(chunk__document__reviewed_at__isnull=True).exists()
    )):
        return hold("source_unverified", **data)
    if not rule.effective_on or (not preview and (c.occurred_on < rule.effective_on or (
        rule.effective_until and c.occurred_on > rule.effective_until
    ))):
        return hold("scope_mismatch", **data)

    conditions = rule.conditions
    facts = {
        "complaint_type": c.complaint_type or None,
        "risk_level": getattr(getattr(c, "risk_assessment", None), "level", None),
        "serious": getattr(getattr(c, "adverse_event", None), "serious", None),
    }
    missing = [key for key in conditions if facts.get(key) is None]
    if missing:
        return hold("missing_input", input_issue="missing_facts", missing_facts=missing, **data)
    if any(facts[k] != v for k, v in conditions.items()):
        return {"decision": "NO_MATCH", "reason": "scope_mismatch", **data}

    if rule.basis not in BASIS_FIELDS:
        return hold("missing_input", input_issue="missing_basis_rule", **data)
    field, case_date_field = BASIS_FIELDS[rule.basis]
    business_date = getattr(c, case_date_field) if case_date_field else None
    raw = getattr(entry, field)
    try:
        value = parse_source(raw) if raw else business_date
        if value is None or (type(value) is date and rule.deadline_unit == "HOURS"):
            issue = "missing_basis_date" if value is None else "missing_basis_time"
            return hold("missing_input", input_issue=issue, **data)
        if business_date and (value.date() if isinstance(value, datetime) else value) != business_date:
            return hold("date_mismatch", **data)
        # A date-only value is never presented as an observed clock time.
        is_date = type(value) is date
        stamp = datetime.combine(value, time.min) if is_date else value
        # A future draft can be simulated on the same facts. The approved application path
        # still enforces the original interval; no rule instance is saved in either path.
        # Applicability was checked against the incident date above, not the trigger clock.
        calculation = calculate_deadline(rule, stamp, enforce_effective=False)
    except (ValidationError, ValueError, ZoneInfoNotFoundError, OverflowError):
        return hold("calculation_unverified", **data)
    if is_date:
        calculation["basis_at"] = value.isoformat()
    return {"decision": "REPORT", "reason": "rule_match", "calculation": calculation,
            "basis_source": raw or value.isoformat(), **data}


def market_rules(user, entry):
    return [rule for rule in rules_for(user).filter(
        Q(device_id=entry.complaint.device_id) | Q(device_id__isnull=True),
        is_example=entry.complaint.is_example,
    ).order_by("name", "-version") if market_code(rule.jurisdiction) == entry.market]


def check_eu(entry, registration, evidence):
    if entry.market not in EU_COUNTRIES:
        return True
    if not registration or registration.eu_assessment not in ("ALIGNED", "NA") or not registration.eu_rationale:
        return False
    if registration.eu_versions != sorted(source.pk for source, _ in evidence):
        return False
    if registration.eu_assessment == "NA":
        return True
    return all(any(source.scope == scope and source.reviewer_id and source.checked_on and
                   (source.is_example or source.official_url) for source, _ in evidence)
               for scope in ("EU", entry.market))


def case_inputs(entry):
    c = entry.complaint
    return {
        "device_id": c.device_id, "occurred_on": str(c.occurred_on), "reported_on": str(c.reported_on),
        "complaint_type": c.complaint_type,
        "risk_level": getattr(getattr(c, "risk_assessment", None), "level", None),
        "serious": getattr(getattr(c, "adverse_event", None), "serious", None),
        **{name: getattr(entry, name) for name, _ in BASIS_FIELDS.values()},
    }


def historical_inputs_changed(entry, latest, evidence, registration):
    if not latest:
        return False
    result = latest.snapshot
    return (
        result.get("case_inputs") != case_inputs(entry)
        or sorted(s["id"] for s in result.get("evidence", [])) != sorted(s.pk for s, _ in evidence)
        or result.get("eu_assessment") != (registration.eu_assessment if registration else "UNKNOWN")
        or result.get("eu_rationale") != (registration.eu_rationale if registration else "")
    )


def automatic_result(entry, user, registration, evidence):
    if entry.market not in COUNTRIES:
        return hold("market_unknown")
    if not check_eu(entry, registration, evidence):
        return hold("eu_review")
    day = entry.complaint.occurred_on
    eligible = [rule for rule in market_rules(user, entry)
                if rule.state in ("APPROVED", "EFFECTIVE")
                and rule.approved_by_id and rule.approved_at and rule.effective_on
                and rule.effective_on <= day and (not rule.effective_until or day <= rule.effective_until)]
    if not eligible:
        return hold("no_rule")
    checked = [(rule, version_result(rule, entry, user)) for rule in eligible]
    possible = [(rule, result) for rule, result in checked if result["decision"] != "NO_MATCH"]
    if len(possible) != 1:
        return hold("ambiguous_rule" if possible else "no_rule")
    return possible[0][1]


@transaction.atomic
def assess(entry, user):
    require_workspace(user)
    # Existing rule lifecycle lock plus product/case locks protect a single consistent read.
    key = UUID(int=0)
    RuleFamilyLock.objects.get_or_create(key=key)
    RuleFamilyLock.objects.filter(pk=key).update(key=key)
    MedicalDevice.objects.select_for_update().get(pk=entry.complaint.device_id)
    CustomerComplaint.objects.select_for_update().get(pk=entry.complaint_id)
    entry = case_markets(user).select_for_update(of=("self",)).get(pk=entry.pk)
    if entry.complaint.status == "CLOSED":
        raise PermissionDenied
    registration = ProductMarket.objects.filter(device=entry.complaint.device, market=entry.market,
                                                is_example=entry.complaint.is_example).first()
    evidence = evidence_for(entry)
    result = automatic_result(entry, user, registration, evidence)
    payload = result.get("rule")
    if result.get("calculation"):
        for citation in payload["citations"]:
            linked = next((source for source, _ in evidence
                           if source.regulation_document_id == citation["document_id"]), None)
            if linked:
                citation["market_source_id"] = linked.pk
    previous = entry.assessments.first()
    result.update(market=entry.market, case_inputs=case_inputs(entry),
                  is_example=entry.complaint.is_example, previous_id=previous.pk if previous else None,
                  evidence=[source_record(source) for source, _ in evidence],
                  eu_assessment=registration.eu_assessment if registration else "UNKNOWN",
                  eu_rationale=registration.eu_rationale if registration else "")
    assessment = MarketAssessment.objects.create(case_market=entry, rule_id=(
        result["calculation"]["rule_id"] if result.get("calculation") else None), actor=user, snapshot=result)
    audit(user, "MARKET_ASSESS", assessment, after={"case_market": entry.pk, "market": entry.market,
          "decision": result["decision"], "rule_version": payload["version"] if payload else None})
    return assessment


def compare(entry, user, baseline, proposed):
    results = [version_result(rule, entry, user, preview=True) for rule in (baseline, proposed)]
    return results, deadline_delta(results)
