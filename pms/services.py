from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Approval, AuditLog, CustomerComplaint, Notification, Profile

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
@transaction.atomic
def transition_complaint(complaint,new_status,user,ip=None):
    CustomerComplaint.objects.select_for_update().get(pk=complaint.pk)
    complaint.refresh_from_db()
    if role(user) not in (Profile.Role.RA_QA,Profile.Role.ADMIN): raise PermissionDenied("RA/QA 또는 관리자만 상태를 변경할 수 있습니다.")
    if TRANSITIONS.get(complaint.status)!=new_status: raise ValidationError(f"허용되지 않은 상태 전이입니다: {complaint.status} → {new_status}")
    if complaint.status=="RISK" and not hasattr(complaint,"risk_assessment"): raise ValidationError("위험평가를 먼저 완료해야 합니다.")
    if complaint.status=="CAPA_DECISION" and getattr(getattr(complaint,"risk_assessment",None),"capa_review_required",False) and not complaint.capas.exists(): raise ValidationError("HIGH 이상 사건은 CAPA를 등록해야 합니다.")
    if complaint.status=="REPORT_REVIEW" and not complaint.reports.exists(): raise ValidationError("규제보고 판단과 체크리스트를 먼저 작성해야 합니다.")
    if complaint.status=="APPROVAL" and not any(a.snapshot.get("integrity")==approval_integrity(complaint) for a in Approval.objects.filter(content_type="CustomerComplaint",object_id=complaint.pk,decision=Approval.Decision.APPROVED)): raise ValidationError("관리자 승인 무결성이 확인되어야 조치를 완료할 수 있습니다. 변경 후 재승인이 필요합니다.")
    if new_status in ("ACTION_COMPLETE","CLOSED") and role(user)!=Profile.Role.ADMIN: raise PermissionDenied("최종 승인·종료는 관리자만 수행할 수 있습니다.")
    old=complaint.status; complaint.status=new_status; complaint.version+=1; complaint.save(update_fields=["status","version","updated_at"]); audit(user,"STATUS_CHANGE",complaint,{"status":old},{"status":new_status},ip); return complaint
def recurrent_warning(complaint,user=None,as_of=None):
    from .safety import rule_reasons
    rules=settings.PMS_RULES; end=as_of or complaint.reported_on
    qs=visible_complaints(user or complaint.reporter).filter(is_example=complaint.is_example,reported_on__lte=end,complaint_type=complaint.complaint_type)
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
@transaction.atomic
def decide_approval(approval,user,decision,reason="",ip=None):
    Approval.objects.select_for_update().get(pk=approval.pk)
    approval.refresh_from_db()
    if role(user)!=Profile.Role.ADMIN: raise PermissionDenied("관리자만 승인 또는 반려할 수 있습니다.")
    if approval.decision!=Approval.Decision.PENDING: raise ValidationError("이미 처리된 승인 요청입니다.")
    if decision not in ("APPROVED","REJECTED"): raise ValidationError("올바른 승인 결정을 선택하세요.")
    if decision=="APPROVED" and approval.content_type=="CustomerComplaint":
        complaint=CustomerComplaint.objects.select_for_update().get(pk=approval.object_id)
        if complaint.status!="APPROVAL" or approval.snapshot.get("integrity")!=approval_integrity(complaint):
            raise ValidationError("승인 요청 이후 자료가 변경되었습니다. 반려 후 재요청하세요.")
    if decision==Approval.Decision.REJECTED and not reason.strip(): raise ValidationError("반려 사유는 필수입니다.")
    approval.decision=decision; approval.reason=reason; approval.decided_by=user; approval.decided_at=timezone.now(); approval.save(); audit(user,decision,approval,after={"reason":reason}); return approval
@transaction.atomic
def request_complaint_approval(complaint,user,ip=None):
    complaint=CustomerComplaint.objects.select_for_update().get(pk=complaint.pk)
    if role(user) not in (Profile.Role.RA_QA,Profile.Role.ADMIN): raise PermissionDenied("RA/QA 또는 관리자만 승인을 요청할 수 있습니다.")
    if complaint.status!="APPROVAL": raise ValidationError("관리자 승인 단계에서만 요청할 수 있습니다.")
    if Approval.objects.filter(content_type="CustomerComplaint",object_id=complaint.pk,decision=Approval.Decision.PENDING).exists(): raise ValidationError("이미 대기 중인 승인 요청이 있습니다.")
    risk=getattr(complaint,"risk_assessment",None)
    snapshot={"complaint_id":complaint.pk,"version":complaint.version,"title":complaint.title,"status":complaint.status,"device":str(complaint.device),"udi":str(complaint.udi),"lot":str(complaint.lot or ""),"risk":{"score":getattr(risk,"score",None),"level":getattr(risk,"level",None)},"capa_ids":list(complaint.capas.values_list("id",flat=True)),"report_ids":list(complaint.reports.values_list("id",flat=True)),"recall_ids":list(complaint.recalls.values_list("id",flat=True))}
    snapshot["integrity"]=approval_integrity(complaint)
    approval=Approval.objects.create(content_type="CustomerComplaint",object_id=complaint.pk,requested_by=user,snapshot=snapshot); audit(user,"APPROVAL_REQUEST",approval,after=snapshot,ip=ip); return approval

def approval_integrity(complaint):
    import hashlib, json
    from django.core.serializers.json import DjangoJSONEncoder
    # Values include related content, so unchanged IDs cannot conceal edits.
    data={"complaint":CustomerComplaint.objects.filter(pk=complaint.pk).values().get()}
    for name in ("capas","reports","recalls","attachments","tasks","rule_applications"):
        data[name]=list(getattr(complaint,name).order_by("pk").values())
    from .models import RiskAssessment, AdverseEvent
    data["risk"]=list(RiskAssessment.objects.filter(complaint=complaint).values())
    data["adverse"]=list(AdverseEvent.objects.filter(complaint=complaint).values())
    return hashlib.sha256(json.dumps(data,sort_keys=True,cls=DjangoJSONEncoder).encode()).hexdigest()
def create_deadline_notifications():
    from .workflow import notify_tasks
    today=timezone.localdate(); count=notify_tasks()
    for c in CustomerComplaint.objects.filter(due_date__lte=today).exclude(status="CLOSED").select_related("assignee","reporter"):
        user=c.assignee or c.reporter
        _,created=Notification.objects.get_or_create(user=user,title=f"사건 #{c.pk} 처리 기한",message=f"{c.due_date}까지 처리가 필요합니다.",defaults={"level":"WARNING"}); count+=int(created)
    return count
