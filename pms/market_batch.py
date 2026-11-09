"""Read-only comparison adapter. Operational results always come from the existing PMS engine."""
from copy import deepcopy
from datetime import date
import json
import logging

from django.core.exceptions import ValidationError

from .market_codes import market_code
from .market_service import BASIS_FIELDS, case_inputs, compare, hold, parse_source, version_result
from .regulatory import normalize_holidays

LOG = logging.getLogger(__name__)
LIMIT = 100
SIDES = ("baseline", "proposed")
RESULT_FIELDS = ("decision", "reason", "basis_date", "due_date", "due_at", "rule_id", "version")


def rule_input(rule):
    return {
        "id": str(rule.pk), "version": rule.version, "market": market_code(rule.jurisdiction),
        "device": str(rule.device_id) if rule.device_id else None, "example": rule.is_example,
        "basis": rule.basis or None, "conditions": rule.conditions, "unit": rule.deadline_unit or "UNKNOWN",
        "day_type": rule.day_type or "UNKNOWN", "days": rule.days, "include_start": rule.include_start,
        "timezone": rule.timezone_name or "UNKNOWN",
        "deadline_time": rule.deadline_time.isoformat() if rule.deadline_time else None,
        "calendar": {"weekend": [5, 6], "holidays": [h["date"] for h in normalize_holidays(rule.holidays)],
                     "verified_from": iso(rule.holiday_verified_from), "verified_until": iso(rule.holiday_verified_until),
                     "checked_on": iso(rule.holiday_checked_on)},
    }


def iso(value):
    return value.isoformat() if value is not None else None


def case_input(entry, rules, results):
    snapshot = case_inputs(entry)
    bases, recorded = {}, {}
    for key, (raw, business_day) in BASIS_FIELDS.items():
        recorded[key] = snapshot.get(business_day) if business_day else None
        value = snapshot[raw] or recorded[key]
        try:
            bases[key] = parse_source(value).isoformat() if value else None
        except ValueError:
            bases[key] = value
    # Source access and rule metadata are checked in Django. Scope, conditions and
    # calendar arithmetic are evaluated independently by the native core.
    holds = [
        r["reason"] if r["reason"] == "source_unverified" or (
            r["decision"] == "HOLD" and r["reason"] == "scope_mismatch" and not rule.effective_on
        ) else None
        for rule, r in zip(rules, results)
    ]
    return {"id": str(entry.complaint_id), "device": str(entry.complaint.device_id),
            "example": entry.complaint.is_example, "bases": bases, "business_dates": recorded,
            "facts": {k: snapshot[k] for k in ("complaint_type", "risk_level", "serious")}, "holds": holds}


def outcome(rule, result, entry):
    calculation = result.get("calculation")
    basis = None
    if calculation:
        basis = calculation["basis_at"][:10]
    elif result["reason"] == "calculation_unverified":
        raw = entry["bases"].get(rule.basis)
        if raw and len(raw) == 10:
            try:
                basis = date.fromisoformat(raw).isoformat()
            except ValueError:
                pass
    due_at = calculation["due_at"] if calculation else None
    return {"decision": result["decision"], "reason": result["reason"], "basis_date": basis,
            "due_at": due_at, "due_date": due_at[:10] if due_at else None,
            "rule_id": str(rule.pk), "version": rule.version}


def changes(before, after):
    left, right = before["decision"], after["decision"]
    review = bool({"HOLD", "unsupported"} & {left, right})
    flags = ["decision_changed"] if not review and left != right else []
    delta = None
    if before["due_date"] and after["due_date"]:
        delta = (date.fromisoformat(after["due_date"]) - date.fromisoformat(before["due_date"])).days
        if delta:
            flags.append("earlier" if delta < 0 else "later")
        elif before["due_at"] != after["due_at"]:
            flags.append("time_changed")
    elif before["due_date"]:
        flags.append("deadline_removed")
    elif after["due_date"]:
        flags.append("deadline_added")
    if review:
        flags.append("review_required")
    return {"changes": flags or ["unchanged"], "delta_days": delta}


def native_engine():
    try:
        import pms_rule_batch
    except (ImportError, OSError):
        return None
    engine = getattr(pms_rule_batch, "run_json", None)
    return engine if callable(engine) else None


def apply_native(rows, response, market):
    if (response["schema_version"] != 1 or response["market"] != market
            or [r["case_id"] for r in response["results"]] != [r["case_id"] for r in rows]):
        raise ValueError("unexpected native result envelope")
    # Validate the entire response before using any row.
    for native in response["results"]:
        for side in SIDES:
            result = native[side]
            if not isinstance(result, dict) or any(field not in result for field in RESULT_FIELDS):
                raise ValueError("incomplete native result")
    for row, native in zip(rows, response["results"]):
        for side in SIDES:
            if row[side]["reason"] == "baseline_unavailable":
                continue
            candidate = native[side]
            if candidate["decision"] == "unsupported":
                row["engines"][side] = {"name": "python", "fallback": candidate["reason"]}
                continue
            row["engines"][side] = {"name": "cpp_verified", "fallback": None}
            for field in RESULT_FIELDS:
                if row[side][field] != candidate[field]:
                    row["mismatches"].append({"side": side, "field": field,
                                              "python": row[side][field], "cpp": candidate[field]})
        if not row["mismatches"] and all(row["engines"][side]["name"] == "cpp_verified" for side in SIDES):
            for field in ("changes", "delta_days"):
                if row[field] != native[field]:
                    row["mismatches"].append({"side": "comparison", "field": field,
                                              "python": row[field], "cpp": native[field]})
        if row["mismatches"]:
            row["changes"] = [flag for flag in row["changes"] if flag != "unchanged"]
            if "review_required" not in row["changes"]:
                row["changes"].append("review_required")
            for side in SIDES:
                if row["engines"][side]["name"] == "cpp_verified":
                    row["engines"][side]["name"] = "cpp_disagreement"


def baseline_applies(rule, entry):
    case = entry.complaint
    return (rule.approved_by_id and rule.approved_at and rule.effective_on
            and rule.effective_on <= case.occurred_on
            and (rule.state != "RETIRED" or rule.effective_until)
            and (not rule.effective_until or case.occurred_on <= rule.effective_until)
            and (not rule.device_id or rule.device_id == case.device_id)
            and rule.is_example == case.is_example)


def run(entries, rules, user, market, *, enforce_baseline=False):
    rows, inputs = [], []
    for entry in entries:
        baseline_unavailable = enforce_baseline and not baseline_applies(rules[0], entry)
        if baseline_unavailable:
            results = [hold("baseline_unavailable"), version_result(rules[1], entry, user, preview=True)]
        else:
            results, _ = compare(entry, user, *rules)
        payload = case_input(entry, rules, results)
        if baseline_unavailable:
            # The native protocol supports a scope hold. Preserve the more specific
            # Python reason and do not treat this side as natively verified.
            payload["holds"][0] = "scope_mismatch"
        inputs.append(payload)
        before, after = [outcome(rule, result, payload) for rule, result in zip(rules, results)]
        rows.append({"case_id": payload["id"], "baseline": before, "proposed": after,
                     "mismatches": [], **changes(before, after),
                     "explanations": {
                         side: explain(rule, result, payload) for side, rule, result in zip(SIDES, rules, results)
                     }})
    native = native_engine()
    fallback = "module_missing" if native is None else "native_error"
    for row in rows:
        row["engines"] = {side: {
            "name": "python", "fallback": "baseline_unavailable" if row[side]["reason"] == "baseline_unavailable" else fallback
        } for side in SIDES}
    if native is None:
        return rows
    try:
        native_rules = [rule_input(rule) for rule in rules]
        # Python TimeField supports fractional seconds; v1 requires whole seconds.
        if any(r["deadline_time"] and len(r["deadline_time"]) != 8 for r in native_rules):
            for row in rows:
                for side in SIDES:
                    if row[side]["reason"] != "baseline_unavailable":
                        row["engines"][side]["fallback"] = "unsupported_method"
            return rows
        request = {"schema_version": 1, "market": market, "cases": inputs, "rules": native_rules}
        response = json.loads(native(json.dumps(request, ensure_ascii=False)))
        # Stage the native evaluation so a malformed module output cannot leave partial results.
        staged = deepcopy(rows)
        apply_native(staged, response, market)
        return staged
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, ValidationError) as exc:
        LOG.warning("Market batch native evaluation failed (%s)", type(exc).__name__)
        return rows


def explain(rule, result, payload):
    # Only the structured comparison inputs are retained, never the case narrative.
    evaluated = result["decision"] in ("REPORT", "NO_MATCH") or result["reason"] in (
        "missing_input", "date_mismatch", "calculation_unverified",
    )
    conditions = []
    if evaluated:
        for field, expected in rule.conditions.items():
            actual = payload["facts"].get(field)
            status = "condition_unknown" if actual is None else "condition_match" if actual == expected else "condition_diff"
            conditions.append({"field": field, "expected": expected, "actual": actual, "status": status})
    calculation = result.get("calculation") or {}
    return {
        "conditions": conditions,
        "basis": rule.basis,
        "basis_input": payload["bases"].get(rule.basis) if evaluated else None,
        "input_issue": result.get("input_issue"),
        "excluded": calculation.get("excluded", []),
        "detail_unavailable": not evaluated,
    }
