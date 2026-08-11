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
    qs=CustomerComplaint.objects.select_related("device","reporter","lot")
    return qs.filter(reporter=user) if role(user)==Profile.Role.STAFF else qs
@transaction.atomic
def transition_complaint(complaint,new_status,user,ip=None):
    if role(user) not in (Profile.Role.RA_QA,Profile.Role.ADMIN): raise PermissionDenied("RA/QA 또는 관리자만 상태를 변경할 수 있습니다.")
    if TRANSITIONS.get(complaint.status)!=new_status: raise ValidationError(f"허용되지 않은 상태 전이입니다: {complaint.status} → {new_status}")
    if new_status in ("ACTION_COMPLETE","CLOSED") and role(user)!=Profile.Role.ADMIN: raise PermissionDenied("최종 승인·종료는 관리자만 수행할 수 있습니다.")
    old=complaint.status; complaint.status=new_status; complaint.version+=1; complaint.save(update_fields=["status","version","updated_at"]); audit(user,"STATUS_CHANGE",complaint,{"status":old},{"status":new_status},ip); return complaint
def recurrent_warning(complaint):
    rules=settings.PMS_RULES; now=timezone.localdate(); qs=CustomerComplaint.objects.exclude(pk=complaint.pk)
    lot_count=qs.filter(lot=complaint.lot,complaint_type=complaint.complaint_type,reported_on__gte=now-timedelta(days=rules["LOT_WINDOW_DAYS"])).count()+1 if complaint.lot_id else 0
    device_count=qs.filter(device=complaint.device,complaint_type=complaint.complaint_type,reported_on__gte=now-timedelta(days=rules["DEVICE_WINDOW_DAYS"])).count()+1
    critical=CustomerComplaint.objects.filter(pk=complaint.pk,risk_assessment__level="CRITICAL").exists()
    reasons=[]
    if lot_count>=rules["LOT_THRESHOLD"]: reasons.append("동일 LOT 30일 내 유사 불만 임계치 도달")
    if device_count>=rules["DEVICE_THRESHOLD"]: reasons.append("동일 제품 90일 내 동일 유형 불만 임계치 도달")
    if critical: reasons.append("CRITICAL 사건 발생")
    return reasons
@transaction.atomic
def decide_approval(approval,user,decision,reason="",ip=None):
    if role(user)!=Profile.Role.ADMIN: raise PermissionDenied("관리자만 승인 또는 반려할 수 있습니다.")
    if approval.decision!=Approval.Decision.PENDING: raise ValidationError("이미 처리된 승인 요청입니다.")
    if decision==Approval.Decision.REJECTED and not reason.strip(): raise ValidationError("반려 사유는 필수입니다.")
    approval.decision=decision; approval.reason=reason; approval.decided_by=user; approval.decided_at=timezone.now(); approval.save(); audit(user,decision,approval,after={"reason":reason}); return approval
def create_deadline_notifications():
    today=timezone.localdate(); count=0
    for c in CustomerComplaint.objects.filter(due_date__lte=today).exclude(status="CLOSED").select_related("assignee","reporter"):
        user=c.assignee or c.reporter
        _,created=Notification.objects.get_or_create(user=user,title=f"사건 #{c.pk} 처리 기한",message=f"{c.due_date}까지 처리가 필요합니다.",defaults={"level":"WARNING"}); count+=int(created)
    return count
