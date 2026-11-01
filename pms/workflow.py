"""Shared domain operations for both HTML forms and management commands."""
from datetime import date, datetime, time, timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import (WorkTask, TaskHistory, CAPA, CAPAEvaluation, Recall, RecallRecipient,
                     RecoveryEntry, RecallContact, ReportingRule, RuleApplication,
                     CustomerComplaint, Notification, Attachment)
from .services import role, visible_complaints, audit


def privileged(user):
    if role(user) not in ("RA_QA","ADMIN"): raise PermissionDenied("RA/QA 또는 관리자 권한이 필요합니다.")


def tasks_for(user):
    qs=WorkTask.objects.select_related("complaint","assignee","capa","recall")
    if role(user)=="STAFF":
        # An assignment never grants access to somebody else's case.
        qs=qs.filter(assignee=user,complaint__in=visible_complaints(user))
    return qs


def task_state(obj):
    return {"assignee_id":obj.assignee_id,"due_at":obj.due_at.isoformat(),"status":obj.status,
            "title":obj.title,"description":obj.description,"priority":obj.priority,
            "completed_at":obj.completed_at.isoformat() if obj.completed_at else None}


@transaction.atomic
def save_task(obj,user):
    old=WorkTask.objects.select_for_update().get(pk=obj.pk) if obj.pk else None
    if role(user)=="STAFF":
        if not old or not tasks_for(user).filter(pk=old.pk).exists(): raise PermissionDenied
        if any(getattr(old,k)!=getattr(obj,k) for k in ("assignee_id","due_at","title","description","priority","complaint_id","capa_id","recall_id")):
            raise PermissionDenied("담당 직원은 상태만 변경할 수 있습니다.")
    else: privileged(user)
    # Validate required fields before dereferencing relations or checking tzinfo,
    # so service callers receive a validation error instead of an AttributeError.
    obj.full_clean()
    if role(obj.assignee)=="STAFF" and obj.complaint.reporter_id != obj.assignee_id:
        raise ValidationError("STAFF 담당자는 본인 접수 사건만 배정할 수 있습니다.")
    before=task_state(old) if old else {}
    if old and old.status=="DONE" and obj.status!="DONE" and role(user)=="STAFF":
        raise ValidationError("완료 업무의 재개는 RA/QA 또는 관리자에게 요청하세요.")
    if obj.status=="DONE":
        obj.completed_at=old.completed_at if old and old.status=="DONE" else timezone.now()
    else:
        obj.completed_at=None
    if not timezone.is_aware(obj.due_at): raise ValidationError("마감 시각에는 시간대가 필요합니다.")
    obj.full_clean(); obj.save()
    after=task_state(obj)
    if before!=after:
        TaskHistory.objects.create(task=obj,actor=user,before=before,after=after)
        audit(user,"TASK_CHANGE",obj,before,after)
    return obj


def notify_tasks(now=None):
    now=now or timezone.now(); horizon=now+timedelta(days=settings.TASK_DUE_SOON_DAYS); count=0
    for task in WorkTask.objects.filter(due_at__lte=horizon).exclude(status="DONE").iterator():
        kind="OVERDUE" if task.due_at<now else "SOON"
        key=f"task:{task.pk}:{task.assignee_id}:{task.due_at.isoformat()}:{kind}"
        _,created=Notification.objects.get_or_create(dedupe_key=key,defaults={"user":task.assignee,"title":f"업무 {'기한 초과' if kind=='OVERDUE' else '마감 임박'}: {task.title}"[:200],"message":f"업무 #{task.pk} / {timezone.localtime(task.due_at):%Y-%m-%d %H:%M %Z}","level":"WARNING","due_at":task.due_at})
        count+=int(created)
    return count


@transaction.atomic
def evaluate_capa(capa,user,data,evidence=()):
    privileged(user)
    CustomerComplaint.objects.select_for_update().get(pk=capa.complaint_id)
    capa=CAPA.objects.select_for_update().get(pk=capa.pk)
    if capa.status=="CLOSED": raise ValidationError("종결 CAPA는 평가할 수 없습니다.")
    required=("action_result","criteria","scheduled_on","evaluated_on","verdict","rationale")
    if any(not data.get(k) or (isinstance(data.get(k),str) and not data[k].strip()) for k in required): raise ValidationError("조치 결과·기준·예정일·평가일·판정·근거는 필수입니다.")
    if data["verdict"] not in ("PASS","FAIL"): raise ValidationError("올바른 판정을 선택하세요.")
    if data["evaluated_on"]>timezone.localdate(): raise ValidationError("평가일은 미래일 수 없습니다.")
    files=list(evidence)
    if any(f.complaint_id!=capa.complaint_id or f.scan_status!="PASSED" for f in files): raise ValidationError("동일 사건의 검사 통과 증빙만 연결할 수 있습니다.")
    ev=CAPAEvaluation(capa=capa,evaluator=user,**{k:data[k] for k in required}); ev.full_clean(); ev.save(); ev.evidence.set(files)
    capa.action_result=data["action_result"]; capa.evaluation_criteria=data["criteria"]; capa.evaluation_due=data["scheduled_on"]; capa.status="EFFECTIVENESS"; capa.save()
    if ev.verdict=="FAIL":
        owner=capa.owner if role(capa.owner)!="STAFF" or capa.complaint.reporter_id==capa.owner_id else user
        task=WorkTask(complaint=capa.complaint,capa=capa,assignee=owner,title=f"CAPA 재조치: {capa.title}"[:200],description=f"효과성 평가 #{ev.pk} 미흡. 재조치 및 재평가 필요",priority="HIGH",due_at=timezone.now()+timedelta(days=settings.TASK_DUE_SOON_DAYS))
        save_task(task,user); ev.followup=task; ev.save(update_fields=["followup"])
    audit(user,"CAPA_EVALUATE",ev,after={"capa":capa.pk,"verdict":ev.verdict,"evidence_ids":[f.pk for f in files]})
    return ev


@transaction.atomic
def close_capa(capa,user):
    privileged(user)
    CustomerComplaint.objects.select_for_update().get(pk=capa.complaint_id)
    capa=CAPA.objects.select_for_update().get(pk=capa.pk)
    if capa.tasks.exclude(status="DONE").exists(): raise ValidationError("재조치를 포함한 연결 업무를 먼저 완료하세요.")
    capa.status="CLOSED"; capa.full_clean(); capa.save(); audit(user,"CAPA_CLOSE",capa); return capa


@transaction.atomic
def save_recipient(obj,user):
    privileged(user)
    if obj.recall.complaint_id: CustomerComplaint.objects.select_for_update().get(pk=obj.recall.complaint_id)
    Recall.objects.select_for_update().get(pk=obj.recall_id)
    if obj.pk:
        old=RecallRecipient.objects.select_for_update().get(pk=obj.pk)
        if any(getattr(old,k)!=getattr(obj,k) for k in ("recall_id","lot_id","partner_id","unit","target_quantity")):
            raise ValidationError("대상 원장은 변경할 수 없습니다. 통보·회신만 수정하세요.")
        # A form or caller may hold an instance loaded before a recovery. Never
        # overwrite the atomic reservation counter with that stale value.
        obj.recovered_total=old.recovered_total
    elif obj.recovered_total:
        raise ValidationError("회수 수량은 부분 회수 이력으로 등록하세요.")
    today=timezone.localdate()
    if any(value and value>today for value in (obj.notified_on,obj.replied_on)):
        raise ValidationError("통보일과 회신일은 미래일 수 없습니다.")
    if obj.replied_on and (not obj.notified_on or obj.replied_on<obj.notified_on):
        raise ValidationError("회신일은 통보일 이후여야 합니다.")
    if obj.reply_status in ("REPLIED","DECLINED") and not obj.replied_on:
        raise ValidationError("회신 상태를 변경하려면 회신일을 입력하세요.")
    if obj.reply_status=="DECLINED" and not obj.unrecovered_reason.strip():
        raise ValidationError("회수 불가인 경우 미회수 사유를 입력하세요.")
    obj.full_clean(); obj.save(); audit(user,"RECALL_RECIPIENT",obj,after={"target":obj.target_quantity,"unit":obj.unit,"reply_status":obj.reply_status,"notified_on":str(obj.notified_on),"replied_on":str(obj.replied_on)})
    return obj


@transaction.atomic
def record_recovery(recipient,user,quantity,recovered_on,submission_key=None):
    privileged(user)
    if recipient.recall.complaint_id: CustomerComplaint.objects.select_for_update().get(pk=recipient.recall.complaint_id)
    if not isinstance(quantity,int) or isinstance(quantity,bool) or quantity<=0: raise ValidationError("회수 수량은 양수 정수여야 합니다.")
    if not isinstance(recovered_on,date) or isinstance(recovered_on,datetime) or recovered_on>timezone.localdate():
        raise ValidationError("회수 일자는 오늘 또는 과거 날짜여야 합니다.")
    # Lock parent for PostgreSQL; conditional UPDATE also enforces capacity on SQLite.
    obj=RecallRecipient.objects.select_for_update().get(pk=recipient.pk)
    if submission_key is not None:
        existing=RecoveryEntry.objects.filter(submission_key=submission_key).first()
        if existing:
            if (existing.recipient_id,existing.quantity,existing.recovered_on,existing.actor_id)!=(obj.pk,quantity,recovered_on,user.pk):
                raise ValidationError("이미 사용한 회수 등록 키입니다. 새 회수 화면을 여세요.")
            return existing
    changed=RecallRecipient.objects.filter(pk=obj.pk,recovered_total__lte=F("target_quantity")-quantity).update(recovered_total=F("recovered_total")+quantity)
    if changed!=1: raise ValidationError("회수 대상 수량을 초과했습니다.")
    entry=RecoveryEntry(recipient=obj,quantity=quantity,recovered_on=recovered_on,actor=user,submission_key=submission_key); entry.full_clean(); entry.save()
    audit(user,"RECALL_RECOVERY",entry,after={"recipient":obj.pk,"quantity":quantity,"unit":obj.unit})
    return entry


@transaction.atomic
def record_contact(obj,user):
    privileged(user)
    if not obj.contacted_at or not timezone.is_aware(obj.contacted_at) or obj.contacted_at>timezone.now():
        raise ValidationError("연락 일시는 시간대를 포함한 현재 또는 과거 시각이어야 합니다.")
    obj.actor=user; obj.full_clean(); obj.save()
    audit(user,"RECALL_CONTACT",obj,after={"recipient":obj.recipient_id,"method":obj.method,"contacted_at":obj.contacted_at.isoformat()}); return obj


def recall_totals(recall):
    totals={}
    for row in recall.recipients.all():
        item=totals.setdefault(row.unit,{"target":0,"recovered":0,"remaining":0})
        item["target"]+=row.target_quantity; item["recovered"]+=row.recovered_quantity
        item["remaining"]+=row.remaining_quantity
    return totals


def validate_rule(rule):
    from .regulatory import validate_rule_content
    return validate_rule_content(rule)


def create_rule(rule,user):
    from .regulatory import save_draft
    return save_draft(rule,user,rule.change_reason)


def matches(rule,complaint):
    from .regulatory import matches_case
    return matches_case(rule,complaint)


def apply_rule(complaint,user,name,reason):
    # Legacy callers may not bypass review, explicit version choice, and preview confirmation.
    privileged(user)
    raise ValidationError("보고 규칙 화면에서 승인·시행 버전을 선택하고 변경 전후 미리보기를 확인한 뒤 적용하세요.")
