"""Services for market applications. Dates and regulatory judgments are user records."""
from datetime import datetime, time

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from .approval_integrity import digest
from .file_security import safe_attachment_bytes
from .foreign_models import ForeignApplication, ForeignDocument, ForeignResult, ForeignSubmission, ForeignSupplement
from .models import Approval, Attachment, RegulatoryProfile, WorkTask
from .ra_services import check_training_gate, require_admin, require_ra
from .services import audit, role
from .workflow import save_task

STAGE = ForeignApplication.Stage
CHECKLIST = {
    "US": ("영문 사용목적", "라벨·IFU", "위험관리", "소프트웨어 검증", "미국 제출 범위 검토"),
    "EU": ("영문 사용목적", "라벨·IFU", "위험관리", "소프트웨어 검증", "EU 기술문서 범위 검토"),
}
APP_FIELDS = ("profile", "market", "title", "kind", "previous", "model_scope", "release", "intended_use",
              "classification", "pathway", "rationale", "owner", "target_on", "is_example")
DOC_FIELDS = ("title", "version", "owner", "applicability", "rationale", "status", "evidence")


def lock_application(pk):
    profile_id = ForeignApplication.objects.values_list("profile_id", flat=True).get(pk=pk)
    RegulatoryProfile.objects.select_for_update().get(pk=profile_id)
    return ForeignApplication.objects.select_for_update().get(pk=pk)


def require_stage(case, *stages):
    if case.stage not in stages:
        raise ValidationError("현재 단계에서 수행할 수 없는 작업입니다.")


def validate_owner(user):
    if not user.is_active or role(user) not in ("RA_QA", "ADMIN"):
        raise ValidationError("활성 RA/QA 또는 관리자 담당자를 지정하세요.")


def evidence_metadata(attachment):
    return {
        "id": attachment.pk, "name": attachment.original_name,
        "sha256": attachment.sha256, "scan_status": attachment.scan_status,
    }


def evidence(case, attachment):
    current = Attachment.objects.filter(
        pk=attachment.pk if attachment else None, ra_profile_id=case.profile_id, scan_status="PASSED",
    ).first()
    if not current:
        raise ValidationError("같은 시장 프로필에 등록된 검사 통과 증빙이 필요합니다.")
    try:
        safe_attachment_bytes(current)
    except PermissionDenied as exc:
        raise ValidationError("증빙 원본을 찾을 수 없거나 파일 무결성을 확인할 수 없습니다.") from exc
    return evidence_metadata(current)


def approvals(case):
    return Approval.objects.filter(content_type="ForeignApplication", object_id=case.pk).order_by("-pk")


def invalidate_review(case):
    approvals(case).filter(superseded=False, decision__in=("PENDING", "APPROVED")).update(superseded=True)


def manifest(case, validate=False):
    documents = []
    for document in case.documents.select_related("evidence").order_by("pk"):
        item = model_to_dict(document, fields=DOC_FIELDS)
        item["id"] = document.pk
        if validate and document.applicability == "UNVERIFIED":
            raise ValidationError("모든 체크리스트 항목의 적용 여부를 검토하세요.")
        if validate and document.applicability == "APPLIES":
            if document.status != "READY" or not document.version:
                raise ValidationError("적용 문서의 버전 및 준비 완료 상태가 필요합니다.")
            item["file"] = evidence(case, document.evidence)
        elif document.evidence:
            item["file"] = evidence_metadata(document.evidence)
        documents.append(item)
    if validate and not any(item["applicability"] == "APPLIES" for item in documents):
        raise ValidationError("제출 범위에 적용 문서를 하나 이상 지정하세요.")
    scope = model_to_dict(case, fields=APP_FIELDS)
    scope["device"] = case.profile.device_id
    scope["release_version"] = case.release.version if case.release_id else ""
    scope["target_on"] = case.target_on.isoformat() if case.target_on else None
    return {"scope": scope, "documents": documents}


@transaction.atomic
def save_application(user, values, pk=None):
    require_ra(user)
    case = lock_application(pk) if pk else ForeignApplication(created_by=user)
    require_stage(case, STAGE.PREPARATION, STAGE.REVIEW)
    before = manifest(case)["scope"] if pk else {}
    if pk and any(values[field] != getattr(case, field) for field in ("profile", "market", "is_example")):
        raise ValidationError("등록된 신청의 시장·프로필·시연 구분은 변경할 수 없습니다.")
    for field in APP_FIELDS:
        setattr(case, field, values[field])
    validate_owner(case.owner)
    if case.profile.jurisdiction != case.market or case.profile.is_example != case.is_example:
        raise ValidationError("관할이 US 또는 EU인 동일 시장·시연 구분의 제품 규제 프로필을 선택하세요.")
    if not (case.model_scope or case.release_id):
        raise ValidationError("적용 모델 또는 소프트웨어 릴리스를 지정하세요.")
    if case.release_id and case.release.device_id != case.profile.device_id:
        raise ValidationError("릴리스와 제품이 일치해야 합니다.")
    previous = case.previous
    if previous and (previous.pk == pk or previous.profile.device_id != case.profile.device_id
                     or previous.market != case.market or previous.is_example != case.is_example):
        raise ValidationError("이전 신청은 동일 제품·시장·시연 구분의 별도 신청이어야 합니다.")
    if pk and previous and previous.pk >= pk:
        raise ValidationError("등록 순서가 앞선 신청만 연결할 수 있습니다.")
    case.full_clean()
    case.save()
    if not pk:
        ForeignDocument.objects.bulk_create([
            ForeignDocument(application=case, owner=case.owner, title=title) for title in CHECKLIST[case.market]
        ])
    after = manifest(case)["scope"]
    if pk and before != after:
        invalidate_review(case)
    audit(user, "FOREIGN_APPLICATION_SAVE", case, before=before, after=after)
    return case


@transaction.atomic
def save_document(user, case_id, values, pk=None):
    require_ra(user)
    case = lock_application(case_id)
    document = case.documents.get(pk=pk) if pk else ForeignDocument(application=case)
    validate_owner(values["owner"])
    if values["applicability"] != "UNVERIFIED" and not values["rationale"]:
        raise ValidationError("적용 여부의 판단 근거가 필요합니다.")
    if values["evidence"]:
        evidence(case, values["evidence"])
    if values["status"] == "READY" and values["applicability"] == "APPLIES":
        if not values["version"]:
            raise ValidationError("준비 완료 문서의 버전이 필요합니다.")
        evidence(case, values["evidence"])
    before = model_to_dict(document, fields=DOC_FIELDS) if pk else {}
    for field in DOC_FIELDS:
        setattr(document, field, values[field])
    document.full_clean()
    document.save()
    after = model_to_dict(document, fields=DOC_FIELDS)
    if before != after and case.stage == STAGE.REVIEW:
        invalidate_review(case)
    audit(user, "FOREIGN_DOCUMENT_SAVE", document, before=before, after=after)
    return document


@transaction.atomic
def operate(user, pk, action, values):
    require_ra(user)
    case = lock_application(pk)
    old_stage = case.stage
    event = {}
    if action == "review":
        require_stage(case, STAGE.PREPARATION, STAGE.REVIEW)
        content = manifest(case, validate=True)
        current = approvals(case).first()
        if current and not current.superseded and current.decision in ("PENDING", "APPROVED") and current.snapshot.get("hash") == digest(content):
            raise ValidationError("현재 범위의 검토 요청 또는 승인이 있습니다.")
        approvals(case).filter(decision="PENDING").update(superseded=True)
        approval = Approval.objects.create(content_type="ForeignApplication", object_id=pk, requested_by=user,
                                snapshot={"schema": 2, "hash": digest(content), "content": content})
        event["approval_id"] = approval.pk
        case.stage = STAGE.REVIEW
    elif action in ("approve", "reject"):
        require_admin(user)
        require_stage(case, STAGE.REVIEW)
        approval = approvals(case).first()
        if not approval or approval.decision != "PENDING" or approval.superseded:
            raise ValidationError("검토 대기 중인 요청이 필요합니다.")
        if action == "approve":
            if case.created_by_id == user.pk:
                raise ValidationError("작성자와 최종 승인자를 분리하세요.")
            check_training_gate(case, user)
            if approval.snapshot.get("hash") != digest(manifest(case, validate=True)):
                raise ValidationError("제출 범위가 변경되었습니다. 내부 검토를 다시 요청하세요.")
        if action == "reject" and not values.get("reason"):
            raise ValidationError("반려 사유를 입력하세요.")
        approval.decision = "APPROVED" if action == "approve" else "REJECTED"
        approval.decided_by = user
        approval.decided_at = timezone.now()
        approval.reason = values.get("reason", "")
        approval.save()
        audit(user, "FOREIGN_INTERNAL_DECISION", approval, after={"decision": approval.decision})
        event["approval_id"] = approval.pk
    elif action == "submit":
        require_stage(case, STAGE.REVIEW)
        approval = approvals(case).first()
        if not approval or approval.superseded or approval.decision != "APPROVED" or approval.snapshot.get("hash") != digest(manifest(case, validate=True)):
            raise ValidationError("현재 범위의 관리자 내부 승인이 필요합니다.")
        proof = evidence(case, values["evidence"])
        submission = ForeignSubmission(application=case, approval=approval, **values,
                                       manifest={**approval.snapshot["content"], "receipt": proof})
        submission.full_clean()
        submission.save()
        event.update(submission_id=submission.pk, reference=submission.reference)
        case.stage = STAGE.SUBMITTED
    elif action == "supplement":
        require_stage(case, STAGE.SUBMITTED)
        validate_owner(values["owner"])
        if values["requested_on"] < case.submissions.get().submitted_on:
            raise ValidationError("보완 요청일은 제출일 이후여야 합니다.")
        if values["due_on"] < values["requested_on"]:
            raise ValidationError("회신 기한은 요청일 이후여야 합니다.")
        deadline = timezone.make_aware(datetime.combine(values["due_on"], time(23, 59)))
        task = save_task(WorkTask(ra_profile=case.profile, assignee=values["owner"],
                                 title=f"해외 인허가 #{pk} 보완 회신", description=values["basis"],
                                 due_at=deadline), user)
        item = ForeignSupplement.objects.create(application=case, task=task, requested_on=values["requested_on"],
                                                due_on=values["due_on"], basis=values["basis"])
        event.update(supplement_id=item.pk, task_id=task.pk)
    elif action == "respond":
        require_stage(case, STAGE.SUBMITTED)
        item = case.supplements.select_related("task").get(pk=values["supplement_id"])
        if item.responded_on or values["responded_on"] < item.requested_on:
            raise ValidationError("이미 회신했거나 회신일이 요청일보다 앞섭니다.")
        evidence(case, values["response"])
        item.response = values["response"]
        item.responded_on = values["responded_on"]
        item.save(update_fields=["response", "responded_on"])
        item.task.status = "DONE"
        save_task(item.task, user)
        event.update(supplement_id=item.pk, response_id=item.response_id)
    elif action == "result":
        require_stage(case, STAGE.SUBMITTED)
        if case.supplements.filter(responded_on__isnull=True).exists():
            raise ValidationError("미회신 보완 요청을 먼저 처리하세요.")
        if values["issued_on"] < case.submissions.get().submitted_on:
            raise ValidationError("결과일은 제출일 이후여야 합니다.")
        if values["expires_on"] and values["expires_on"] < values["issued_on"]:
            raise ValidationError("유효기간 종료일은 결과일 이후여야 합니다.")
        evidence(case, values["evidence"])
        result = ForeignResult(application=case, **values)
        result.full_clean()
        result.save()
        event.update(result_id=result.pk, reference=result.reference)
        case.stage = STAGE.RESULT
    else:
        raise ValidationError("지원하지 않는 작업입니다.")
    if case.stage != old_stage:
        case.save(update_fields=["stage"])
    audit(user, "FOREIGN_" + action.upper(), case, before={"stage": old_stage}, after={"stage": case.stage, **event})
    return case

