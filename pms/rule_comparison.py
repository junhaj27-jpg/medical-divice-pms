"""Read-only comparison of two accessible versions of one reporting rule."""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError

from .regulatory import (
    CONTENT_FIELDS, DISPLAY_LABELS, calculate_deadline, citation_data, json_value,
    matches_case, parse_basis, readiness, validate_rule_content,
)


BASIS_INPUTS = {
    "REPORTED": ("reported_at", "접수 일시", "reported_on"),
    "OCCURRED": ("occurred_at", "발생 일시", "occurred_on"),
    "AWARE": ("aware_at", "인지 일시", None),
    "CUSTOM": ("custom_at", "별도 기준 일시", None),
}


def visible_sources(rule, document_ids):
    return [{**source, "field_label": DISPLAY_LABELS.get(source["field"], source["field"])}
            for source in citation_data(rule) if source["document_id"] in document_ids]


def comparison_rows(baseline, proposed, sources):
    def source_content(citations):
        # Revising a rule copies citations with new row IDs.
        return sorted(
            ({key: value for key, value in source.items() if key != "id"} for source in citations),
            key=lambda source: (source["field"], source["chunk_id"], source["quote"], source["interpretation"]),
        )

    rows = []
    for field in (*CONTENT_FIELDS, "citations"):
        if field in ("change_reason", "origin"):
            continue
        if field == "citations":
            left, right = map(source_content, sources)
        else:
            left, right = (json_value(getattr(rule, field)) for rule in (baseline, proposed))
        if left == right or (left in (None, "", [], {}) and right in (None, "", [], {})):
            status = "동일"
        elif left in (None, "", [], {}):
            status = "추가"
        elif right in (None, "", [], {}):
            status = "삭제"
        else:
            status = "변경"
        rows.append({"field": DISPLAY_LABELS[field], "left": left, "right": right,
                     "status": status, "is_sources": field == "citations"})
    return sorted(rows, key=lambda row: row["status"] == "동일")


def evaluate_version(rule, case, inputs, user, document_ids, sources):
    result = {"rule": rule, "sources": sources, "issues": [], "calculation": None,
              "decision": "추가 확인 필요", "basis_at": None}
    try:
        validate_rule_content(rule)
        if rule.citations.exclude(chunk__document_id__in=document_ids).exists():
            result["issues"].append("조회 가능한 근거 문서를 등록하거나 접근 권한을 확인하세요.")
        else:
            result["issues"].extend(readiness(rule, user))
        if not inputs["jurisdiction"]:
            result["issues"].append("사건 관할을 입력하세요.")
        if rule.is_example and not case.is_example:
            result["issues"].append("예시 규칙은 가상 사례 또는 예시 사건으로 검증하세요.")

        in_jurisdiction = inputs["jurisdiction"] == rule.jurisdiction
        if inputs["jurisdiction"] and rule.jurisdiction and not in_jurisdiction:
            result["reason"] = "입력한 관할과 규칙 관할이 다릅니다."
        elif rule.device_id and not case.device_id:
            result["issues"].append("사건의 대상 제품을 선택하세요.")
        elif "complaint_type" in rule.conditions and not case.complaint_type:
            result["issues"].append("사건 유형을 입력하세요.")
        elif "risk_level" in rule.conditions and not getattr(getattr(case, "risk_assessment", None), "level", None):
            result["issues"].append("사건의 위험등급을 확인하세요.")
        elif "serious" in rule.conditions and not case.pk and case.adverse_event.serious is None:
            result["issues"].append("가상 사례의 중대 여부를 선택하세요.")
        elif not matches_case(rule, case):
            result["reason"] = "사건의 제품 또는 적용 조건이 이 버전과 일치하지 않습니다."
        if result.get("reason"):
            if not result["issues"]:
                result["decision"] = "보고 규칙 적용 대상 아님"
            return result

        if rule.basis not in BASIS_INPUTS:
            result["issues"].append("규칙의 기산점을 확인하세요.")
            return result
        key, label, date_field = BASIS_INPUTS[rule.basis]
        stamp = inputs[key]
        if not stamp:
            result["issues"].append(f"{label}를 입력하세요.")
            return result
        try:
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError
        except ValueError:
            result["issues"].append(f"{label}를 UTC 오프셋을 포함한 ISO 일시로 입력하세요.")
            return result
        if rule.timezone_name:
            basis = parse_basis(stamp, ZoneInfo(rule.timezone_name))
            result["basis_at"] = basis.isoformat()
            if date_field and case.pk and basis.date() != getattr(case, date_field):
                result["issues"].append(f"{label}의 날짜가 사건 기록과 일치하는지 확인하세요.")
        if not result["issues"]:
            result["calculation"] = calculate_deadline(rule, stamp)
            result["decision"] = "보고 규칙 적용 대상"
            result["reason"] = "입력한 관할과 규칙의 제품·적용 조건이 일치합니다."
    except ValidationError as exc:
        result["issues"].extend(exc.messages)
    except OverflowError:
        result["issues"].append("기준 일시와 기한이 계산 가능한 날짜 범위인지 확인하세요.")
    return result


def deadline_delta(results):
    if all(result.get("calculation") for result in results):
        baseline, proposed = (datetime.fromisoformat(result["calculation"]["due_at"]).date()
                              for result in results)
        return (proposed - baseline).days
    return None
