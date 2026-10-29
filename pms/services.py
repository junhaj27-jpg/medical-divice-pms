from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Approval, AuditLog, CustomerComplaint, Notification, Profile
from .approval_integrity import approval_snapshot, approval_invalid_reason
from functools import wraps

def record_blocked(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        try: return fn(*args,**kwargs)
        except ValidationError:
            user=kwargs.get("user") or args[2 if fn.__name__=="transition_complaint" else 1]
            audit(user,"APPROVAL_BLOCKED",args[0],after={"operation":fn.__name__})
            raise
    return wrapped

TRANSITIONS={"RECEIVED":"REVIEW","REVIEW":"AE_DECISION","AE_DECISION":"RISK","RISK":"CAPA_DECISION","CAPA_DECISION":"REPORT_REVIEW","REPORT_REVIEW":"RECALL_REVIEW","RECALL_REVIEW":"APPROVAL","APPROVAL":"ACTION_COMPLETE","ACTION_COMPLETE":"CLOSED"}
SENSITIVE={"password","token","session","anonymous_code","patient"}
def role(user):
    if user.is_superuser: return Profile.Role.ADMIN
    return getattr(getattr(user,"profile",None),"role",Profile.Role.STAFF)
def audit(actor,action,obj=None,before=None,after=None,ip=None):
    def clean(d): return {k:v for k,v in (d or {}).items() if not any(s in k.lower() for s in SENSITIVE)}
    return AuditLog.objects.create(actor=actor if getattr(actor,"is_authenticated",False) else None,action=action,object_type=obj.__class__.__name__ if obj else "",object_id=str(getattr(obj,"pk","")),before=clean(before),after=clean(after),ip_address=ip)
def visible_complaints(user):
    if not user.is_authenticated: return CustomerComplaint.objects.none()
    qs=CustomerComplaint.objects.select_related("device","reporter","lot")
    return qs.filter(reporter=user) if role(user)==Profile.Role.STAFF else qs
@record_blocked
@transaction.atomic
def transition_complaint(complaint,new_status,user,ip=None):
<<<<<<< HEAD
    CustomerComplaint.objects.select_for_update().get(pk=complaint.pk)
    complaint.refresh_from_db()
=======
    original=complaint
    complaint=CustomerComplaint.objects.select_for_update().get(pk=complaint.pk)
>>>>>>> 243e562e399fc29d60693843cff3275fba58fa23
    if role(user) not in (Profile.Role.RA_QA,Profile.Role.ADMIN): raise PermissionDenied("RA/QA 또는 관리자만 상태를 변경할 수 있습니다.")
    if TRANSITIONS.get(complaint.status)!=new_status: raise ValidationError(f"허용되지 않은 상태 전이입니다: {complaint.status} → {new_status}")
    if complaint.status=="RISK" and not hasattr(complaint,"risk_assessment"): raise ValidationError("위험평가를 먼저 완료해야 합니다.")
    if complaint.status=="CAPA_DECISION" and getattr(getattr(complaint,"risk_assessment",None),"capa_review_required",False) and not complaint.capas.exists(): raise ValidationError("HIGH 이상 사건은 CAPA를 등록해야 합니다.")
    if complaint.status=="REPORT_REVIEW" and not complaint.reports.exists(): raise ValidationError("규제보고 판단과 체크리스트를 먼저 작성해야 합니다.")
<<<<<<< HEAD
    if complaint.status in ("APPROVAL","ACTION_COMPLETE") and not approval_is_current(complaint):
        raise ValidationError("관리자 승인 무결성이 확인되어야 진행할 수 있습니다. 변경 사유를 입력하고 재승인을 요청하세요.")
    if new_status in ("ACTION_COMPLETE","CLOSED") and role(user)!=Profile.Role.ADMIN: raise PermissionDenied("최종 승인·종료는 관리자만 수행할 수 있습니다.")
    old=complaint.status; complaint.status=new_status; complaint.version+=1; complaint.save(update_fields=["status","version","updated_at"]); audit(user,"STATUS_CHANGE",complaint,{"status":old},{"status":new_status},ip); return complaint
def recurrent_warning(complaint,user=None,as_of=None):
    from .safety import rule_reasons
    rules=settings.PMS_RULES; end=as_of or complaint.reported_on
    qs=visible_complaints(user or complaint.reporter).filter(is_example=complaint.is_example,reported_on__lte=end,complaint_type=complaint.complaint_type)
=======
    if new_status in ("ACTION_COMPLETE","CLOSED"):
        latest=Approval.objects.filter(content_type="CustomerComplaint",object_id=complaint.pk).order_by("-pk").first()
        if not latest or latest.decision!="APPROVED": raise ValidationError("관리자 승인이 완료되어야 조치를 완료할 수 있습니다.")
        invalid=approval_invalid_reason(latest,complaint)
        if invalid: raise ValidationError(invalid)
    if new_status in ("ACTION_COMPLETE","CLOSED") and role(user)!=Profile.Role.ADMIN: raise PermissionDenied("최종 승인·종료는 관리자만 수행할 수 있습니다.")
    old=complaint.status; complaint.status=new_status; complaint.version+=1; complaint.save(update_fields=["status","version","updated_at"]); audit(user,"STATUS_CHANGE",complaint,{"status":old},{"status":new_status},ip)
    original.status=complaint.status;original.version=complaint.version
    return complaint
def recurrent_warning(complaint):
    rules=settings.PMS_RULES; now=timezone.localdate(); qs=CustomerComplaint.objects.exclude(pk=complaint.pk)
    lot_count=qs.filter(lot=complaint.lot,complaint_type=complaint.complaint_type,reported_on__gte=now-timedelta(days=rules["LOT_WINDOW_DAYS"])).count()+1 if complaint.lot_id else 0
    device_count=qs.filter(device=complaint.device,complaint_type=complaint.complaint_type,reported_on__gte=now-timedelta(days=rules["DEVICE_WINDOW_DAYS"])).count()+1
    critical=CustomerComplaint.objects.filter(pk=complaint.pk,risk_assessment__level="CRITICAL").exists()
>>>>>>> 243e562e399fc29d60693843cff3275fba58fa23
    reasons=[]
    for field,window,threshold in (("lot",rules["LOT_WINDOW_DAYS"],rules["LOT_THRESHOLD"]),("device",rules["DEVICE_WINDOW_DAYS"],rules["DEVICE_THRESHOLD"])):
        value=getattr(complaint,field+"_id")
        if not value: continue
        count=qs.filter(**{field+"_id":value},reported_on__gte=end-timedelta(days=window-1)).count()
        configured=dict(settings.SAFETY_RULES,COUNT=threshold,MINIMUM=threshold,LOT_COUNT=threshold)
        if rule_reasons(count,count,field=="lot",rules=configured):
            reasons.append(f"동일 {field.upper()} {window}일 내 유사 불만 임계치 도달 · 안전 신호 분석에서 검토")
    if qs.filter(pk=complaint.pk,risk_assessment__level="CRITICAL").exists(): reasons.append("CRITICAL 사건 발생 · 안전 신호 검토 필요")
    return reasons
@record_blocked
@transaction.atomic
def decide_approval(approval,user,decision,reason="",ip=None):
    Approval.objects.select_for_update().get(pk=approval.pk)
    approval.refresh_from_db()
    if role(user)!=Profile.Role.ADMIN: raise PermissionDenied("관리자만 승인 또는 반려할 수 있습니다.")
    original=approval
    approval=Approval.objects.get(pk=approval.pk)
    case=None
    if approval.content_type=="CustomerComplaint": case=CustomerComplaint.objects.select_for_update().get(pk=approval.object_id)
    approval=Approval.objects.select_for_update().get(pk=approval.pk)
    if approval.superseded: raise ValidationError("대체된 승인 요청입니다. 최신 요청을 확인하세요.")
    if approval.decision!=Approval.Decision.PENDING: raise ValidationError("이미 처리된 승인 요청입니다.")
    if decision not in ("APPROVED","REJECTED"): raise ValidationError("올바른 승인 결정을 선택하세요.")
<<<<<<< HEAD
    if decision=="APPROVED" and approval.content_type=="CustomerComplaint":
        complaint=CustomerComplaint.objects.select_for_update().get(pk=approval.object_id)
        if complaint.status!="APPROVAL" or approval.snapshot.get("integrity")!=approval_integrity(complaint):
            raise ValidationError("승인 요청 이후 자료가 변경되었습니다. 반려 후 재요청하세요.")
=======
    if decision=="APPROVED" and case:
        invalid=approval_invalid_reason(approval,case)
        if invalid: raise ValidationError(invalid)
>>>>>>> 243e562e399fc29d60693843cff3275fba58fa23
    if decision==Approval.Decision.REJECTED and not reason.strip(): raise ValidationError("반려 사유는 필수입니다.")
    approval.decision=decision; approval.reason=reason; approval.decided_by=user; approval.decided_at=timezone.now(); approval.save(); audit(user,decision,approval,after={"decision":decision}); original.decision=decision; return approval
@transaction.atomic
def request_complaint_approval(complaint,user,ip=None,reason=""):
    complaint=CustomerComplaint.objects.select_for_update().get(pk=complaint.pk)
    if role(user) not in (Profile.Role.RA_QA,Profile.Role.ADMIN): raise PermissionDenied("RA/QA 또는 관리자만 승인을 요청할 수 있습니다.")
<<<<<<< HEAD
    if complaint.status not in ("APPROVAL","ACTION_COMPLETE"): raise ValidationError("관리자 승인 또는 조치 완료 단계에서만 요청할 수 있습니다.")
    if Approval.objects.filter(content_type="CustomerComplaint",object_id=complaint.pk,decision=Approval.Decision.PENDING).exists(): raise ValidationError("이미 대기 중인 승인 요청이 있습니다.")
    latest=latest_complaint_approval(complaint)
    if (complaint.status=="ACTION_COMPLETE" or (latest and latest.decision=="APPROVED")) and not reason.strip():
        raise ValidationError("재승인 요청에는 변경·재검토 사유가 필요합니다.")
    if complaint.status=="ACTION_COMPLETE":
        before={"status":complaint.status,"version":complaint.version}
        complaint.status="APPROVAL";complaint.version+=1
        complaint.save(update_fields=["status","version","updated_at"])
        audit(user,"REAPPROVAL_REOPEN",complaint,before,{"status":complaint.status,"reason":reason},ip)
    risk=getattr(complaint,"risk_assessment",None)
    snapshot={"complaint_id":complaint.pk,"version":complaint.version,"title":complaint.title,"status":complaint.status,"device":str(complaint.device),"udi":str(complaint.udi),"lot":str(complaint.lot or ""),"risk":{"score":getattr(risk,"score",None),"level":getattr(risk,"level",None)},"capa_ids":list(complaint.capas.values_list("id",flat=True)),"report_ids":list(complaint.reports.values_list("id",flat=True)),"recall_ids":list(complaint.recalls.values_list("id",flat=True))}
    snapshot["integrity"]=approval_integrity(complaint)
    snapshot["content_integrity"]=approval_integrity(complaint,content_only=True)
    snapshot["integrity_version"]=2
    snapshot["request_reason"]=reason.strip()
    approval=Approval.objects.create(content_type="CustomerComplaint",object_id=complaint.pk,requested_by=user,snapshot=snapshot); audit(user,"APPROVAL_REQUEST",approval,after=snapshot,ip=ip); return approval

def latest_complaint_approval(complaint):
    return Approval.objects.filter(content_type="CustomerComplaint",object_id=complaint.pk).order_by("-created_at","-pk").first()

def approval_is_current(complaint):
    latest=latest_complaint_approval(complaint)
    if not latest or latest.decision!="APPROVED": return False
    content_only=complaint.status=="ACTION_COMPLETE"
    key="content_integrity" if content_only else "integrity"
    return bool(latest.snapshot.get(key)) and latest.snapshot[key]==approval_integrity(complaint,content_only=content_only)

def approval_integrity(complaint,content_only=False):
    import hashlib, json
    from django.core.serializers.json import DjangoJSONEncoder
    # Values include related content, so unchanged IDs cannot conceal edits.
    data={"complaint":CustomerComplaint.objects.filter(pk=complaint.pk).values().get()}
    if content_only:
        # These three fields change during the authorized workflow itself.
        for field in ("status","version","updated_at"): data["complaint"].pop(field,None)
    for name in ("capas","reports","recalls","attachments","tasks","rule_applications"):
        data[name]=list(getattr(complaint,name).order_by("pk").values())
    from .models import RiskAssessment, AdverseEvent
    data["risk"]=list(RiskAssessment.objects.filter(complaint=complaint).values())
    data["adverse"]=list(AdverseEvent.objects.filter(complaint=complaint).values())
    # Child ledgers and evidence links can change without updating their parent.
    from .models import RecallTarget, RecallRecipient, RecoveryEntry, RecallContact, CAPAEvaluation, TaskHistory
    for name,model,filters in (
        ("recall_targets",RecallTarget,{"recall__complaint":complaint}),
        ("recall_recipients",RecallRecipient,{"recall__complaint":complaint}),
        ("recoveries",RecoveryEntry,{"recipient__recall__complaint":complaint}),
        ("recall_contacts",RecallContact,{"recipient__recall__complaint":complaint}),
        ("capa_evaluations",CAPAEvaluation,{"capa__complaint":complaint}),
        ("capa_evidence",CAPAEvaluation.evidence.through,{"capaevaluation__capa__complaint":complaint}),
        ("task_history",TaskHistory,{"task__complaint":complaint}),
    ):
        data[name]=list(model.objects.filter(**filters).order_by("pk").values())
    return hashlib.sha256(json.dumps(data,sort_keys=True,cls=DjangoJSONEncoder).encode()).hexdigest()
=======
    complaint=CustomerComplaint.objects.select_for_update().get(pk=complaint.pk)
    if complaint.status not in ("APPROVAL","ACTION_COMPLETE"): raise ValidationError("관리자 승인 단계에서만 요청할 수 있습니다.")
    pending=Approval.objects.filter(content_type="CustomerComplaint",object_id=complaint.pk,decision="PENDING",superseded=False)
    for old in pending:
        if not approval_invalid_reason(old,complaint): raise ValidationError("이미 대기 중인 승인 요청이 있습니다.")
    # Retain stale requests unchanged; supersession is explicit metadata, never a fabricated decision.
    pending.update(superseded=True)
    snapshot=approval_snapshot(complaint)
    is_reapproval=Approval.objects.filter(content_type="CustomerComplaint",object_id=complaint.pk).exists()
    approval=Approval.objects.create(content_type="CustomerComplaint",object_id=complaint.pk,requested_by=user,snapshot=snapshot)
    audit(user,"REAPPROVAL_REQUEST" if is_reapproval else "APPROVAL_REQUEST",approval,after={"hash":snapshot["hash"],"case_id":complaint.pk},ip=ip); return approval
>>>>>>> 243e562e399fc29d60693843cff3275fba58fa23
def create_deadline_notifications():
    from .workflow import notify_tasks
    today=timezone.localdate(); count=notify_tasks()
    for c in CustomerComplaint.objects.filter(due_date__lte=today).exclude(status="CLOSED").select_related("assignee","reporter"):
        user=c.assignee or c.reporter
        _,created=Notification.objects.get_or_create(user=user,title=f"사건 #{c.pk} 처리 기한",message=f"{c.due_date}까지 처리가 필요합니다.",defaults={"level":"WARNING"}); count+=int(created)
    return count
