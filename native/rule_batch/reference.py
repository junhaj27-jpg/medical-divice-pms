"""Python oracle for validated v1 examples, using the existing PMS calendar calculation."""
from datetime import date, datetime, time
from types import SimpleNamespace

from django.core.exceptions import ValidationError

from pms.market_batch import changes
from pms.market_service import BASIS_FIELDS
from pms.regulatory import deadline_times


def prepare(batch):
    rules = []
    for item in batch["rules"]:
        calendar = item["calendar"]
        rule = SimpleNamespace(
            **{key: item[key] for key in (
                "id", "version", "basis", "conditions", "device", "example", "days", "include_start", "day_type"
            )},
            deadline_unit=item["unit"], timezone_name=item["timezone"], weekend=set(calendar["weekend"]),
            deadline_time=time.fromisoformat(item["deadline_time"]) if item["deadline_time"] else None,
            holidays=calendar["holidays"], effective_on=None, effective_until=None,
            **{field: date.fromisoformat(calendar[key]) if calendar[key] else None for field, key in (
                ("holiday_verified_from", "verified_from"), ("holiday_verified_until", "verified_until"),
                ("holiday_checked_on", "checked_on"),
            )},
        )
        rules.append(rule)
    return batch["market"], rules, batch["cases"]


def evaluate_case(rule, entry, gate):
    result = dict(decision="HOLD", reason="missing_input", basis_date=None, due_date=None, due_at=None,
                  rule_id=rule.id, version=rule.version)

    def set_status(decision, reason):
        result.update(decision=decision, reason=reason)
        return result

    if (rule.device is not None and rule.device != entry["device"]) or rule.example != entry["example"]:
        return set_status("HOLD", "scope_mismatch")
    if gate:
        return set_status("HOLD", gate)
    facts = entry["facts"]
    if any(facts.get(k) is None for k in rule.conditions):
        return result
    if any(facts[k] != v for k, v in rule.conditions.items()):
        return set_status("NO_MATCH", "scope_mismatch")
    raw = entry["bases"].get(rule.basis)
    if rule.basis not in BASIS_FIELDS or raw is None:
        return result
    if (rule.deadline_unit != "DAYS" or rule.day_type not in {"CALENDAR", "BUSINESS"}
            or (rule.day_type == "BUSINESS" and rule.weekend != {5, 6})):
        return set_status("unsupported", "unsupported_method")
    if len(raw) != 10:
        return set_status("unsupported", "unsupported_timestamp")
    if not (rule.timezone_name in {"UTC", "Etc/UTC"}
            or (rule.timezone_name == "Asia/Seoul" and raw >= "2000-01-01")):
        return set_status("unsupported", "unsupported_timezone")
    recorded = entry.get("business_dates", {}).get(rule.basis)
    if recorded and raw != recorded:
        return set_status("HOLD", "date_mismatch")
    result["basis_date"] = raw
    try:
        _, due, _ = deadline_times(rule, datetime.combine(date.fromisoformat(raw), time.min), enforce_effective=False)
    except (ValidationError, OverflowError, ValueError):
        return set_status("HOLD", "calculation_unverified")
    result.update(basis_date=raw, due_date=due.date().isoformat(), due_at=due.isoformat())
    return set_status("REPORT", "rule_match")


def evaluate(prepared):
    market, rules, cases = prepared
    rows = []
    for entry in cases:
        before, after = [evaluate_case(rule, entry, gate) for rule, gate in zip(rules, entry.get("holds", [None, None]))]
        rows.append({"case_id": entry["id"], "baseline": before, "proposed": after, **changes(before, after)})
    return {"schema_version": 1, "market": market, "results": rows}
