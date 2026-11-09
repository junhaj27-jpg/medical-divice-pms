"""Frozen inputs and review events for the market comparison workflow."""
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Exists, OuterRef

from . import market_batch as batch
from . import market_service as svc
from .market_codes import market_code
from .market_models import MarketComparisonResult, MarketComparisonReview, MarketComparisonRun
from .regulation_documents import documents_for
from .regulatory import citation_data, rules_for
from .services import audit, role

FILTERS = ("decision_changed", "earlier", "later", "review_required")
APPROVED = ("APPROVED", "EFFECTIVE", "RETIRED")


def valid_pair(baseline, proposed):
    return (baseline.state in APPROVED and baseline.approved_by_id and baseline.approved_at
            and proposed.state == "DRAFT" and baseline.family_key == proposed.family_key
            and baseline.version < proposed.version)


def runs_for(user):
    visible = svc.case_markets(user)
    hidden_entries = MarketComparisonResult.objects.filter(run_id=OuterRef("pk")).exclude(entry__in=visible)
    rules = rules_for(user).order_by()
    runs = MarketComparisonRun.objects.filter(market__in=svc.allowed_markets(user),
        baseline__in=rules, proposed__in=rules).filter(~Exists(hidden_entries)).select_related("actor")
    # A draft or source may be private to the runner. Market access alone does
    # not grant access to another person's saved source material.
    return runs if role(user) == "ADMIN" else runs.filter(actor=user)


def freeze_rule(rule, visible_document_ids):
    try:
        details = batch.rule_input(rule)
    except ValidationError:
        # Keep the original holiday values for review if old data fails normalization.
        details = {"id": str(rule.pk), "version": rule.version, "conditions": rule.conditions,
                   "basis": rule.basis, "unit": rule.deadline_unit, "day_type": rule.day_type,
                   "timezone": rule.timezone_name, "days": rule.days, "include_start": rule.include_start,
                   "deadline_time": batch.iso(rule.deadline_time),
                   "calendar": {"weekend": [5, 6], "holidays": rule.holidays,
                                "verified_from": batch.iso(rule.holiday_verified_from),
                                "verified_until": batch.iso(rule.holiday_verified_until),
                                "checked_on": batch.iso(rule.holiday_checked_on)}}
    citations = citation_data(rule)
    return {**details, "name": rule.name, "state": rule.state, "example": rule.is_example,
            "effective_on": batch.iso(rule.effective_on), "effective_until": batch.iso(rule.effective_until),
            "change_reason": rule.change_reason, "citations": [c for c in citations if c["document_id"] in visible_document_ids]}


def freeze_sources(entry, document_ids, cited_ids):
    sources = []
    for latest, older in svc.evidence_for(entry):
        for evidence in [latest, *[item for item in older if item.regulation_document_id in cited_ids]]:
            if evidence.regulation_document_id and evidence.regulation_document_id not in document_ids:
                # A linked source can still be market evidence, but a private
                # regulation document must not be disclosed through that link.
                continue
            sources.append({**svc.source_record(evidence), "excerpt": evidence.excerpt,
                            "current_at_run": evidence.pk == latest.pk})
    return sources


@transaction.atomic
def execute(entries, rules, user, market):
    # Freeze the same version the Python and native comparisons receive.
    locked = {r.pk: r for r in rules_for(user).filter(pk__in=[r.pk for r in rules])
              .order_by("pk").select_for_update(of=("self",))}
    rules = [locked.get(r.pk) for r in rules]
    if not rules[0] or not rules[0].approved_at or not rules[0].approved_by_id or rules[0].state not in APPROVED:
        raise ValidationError("batch_no_baseline")
    if not all(rules) or not valid_pair(*rules) or any(market_code(r.jurisdiction) != market for r in rules):
        raise ValidationError("batch_pair_error")
    visible_ids = set(documents_for(user).values_list("pk", flat=True))
    frozen = {side: freeze_rule(rule, visible_ids) for side, rule in zip(batch.SIDES, rules)}
    cited_ids = {c["document_id"] for rule in frozen.values() for c in rule["citations"]}
    rows = batch.run(entries, rules, user, market, enforce_baseline=True)
    run = MarketComparisonRun.objects.create(market=market, actor=user, baseline=rules[0], proposed=rules[1],
                                            rules=frozen)
    for entry, row in zip(entries, rows):
        row["operating_snapshot"] = entry.assessments.values_list("pk", flat=True).first()
        row["legacy_snapshot"] = bool(entry.legacy_application_id)
        row["example"] = entry.complaint.is_example
        row["sources"] = freeze_sources(entry, visible_ids, cited_ids)
        MarketComparisonResult.objects.create(run=run, entry=entry, snapshot=row)
    engines = sorted({engine["name"] for row in rows for engine in row["engines"].values()})
    pending = sum("review_required" in row["changes"] for row in rows)
    audit(user, "MARKET_RULE_BATCH", run, after={
        "market": market, "rules": [{"id": r.pk, "version": r.version} for r in rules],
        "engines": engines, "count": len(rows), "review_count": pending,
        "status": "review_required" if pending else "complete",
    })
    return run


def review_status(result, latest):
    if latest:
        return "comparison_complete" if latest.complete else "review_required"
    return "review_required" if "review_required" in result.snapshot["changes"] else "comparison_pending"


@transaction.atomic
def record_review(result, user, *, note, complete, previous):
    result = MarketComparisonResult.objects.select_for_update().get(pk=result.pk)
    latest = result.reviews.first()
    if previous != (latest.pk if latest else 0):
        return None
    event = MarketComparisonReview.objects.create(result=result, actor=user, note=note, complete=complete)
    audit(user, "MARKET_COMPARISON_REVIEW", result, before={"status": review_status(result, latest)},
          after={"status": review_status(result, event), "market": result.run.market, "event_id": event.pk})
    return event


def latest_review_id():
    return models.Subquery(MarketComparisonReview.objects.filter(result_id=OuterRef("pk")).values("pk")[:1])
