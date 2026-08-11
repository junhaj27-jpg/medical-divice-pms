import json
from pathlib import Path
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import AttachmentForm, ComplaintForm, RecallForm, RiskForm
from .models import *
from .services import audit, recurrent_warning, role, transition_complaint, visible_complaints
def raqa_required(view): return user_passes_test(lambda u: u.is_authenticated and role(u) in (Profile.Role.RA_QA,Profile.Role.ADMIN))(view)
@login_required
def dashboard(request):
    qs=visible_complaints(request.user); risks=RiskAssessment.objects.filter(complaint__in=qs); recalls=Recall.objects.exclude(progress_status="CLOSED")
    monthly=list(qs.extra(select={"month":"strftime('%%Y-%%m', reported_on)"}).values("month").annotate(count=Count("id")).order_by("month")) if "sqlite" in qs.db else []
    context={"total":qs.count(),"open":qs.exclude(status="CLOSED").count(),"overdue":qs.filter(due_date__lt=timezone.localdate()).exclude(status="CLOSED").count(),"high":risks.filter(level__in=["HIGH","CRITICAL"]).count(),"critical":risks.filter(level="CRITICAL").count(),"capas":CAPA.objects.exclude(status="CLOSED").count(),"reports":RegulatoryReport.objects.filter(status__in=["DRAFT","REVIEW"]).count(),"recalls":recalls,"monthly":json.dumps(monthly,default=str),"products":json.dumps(list(qs.values(label=models.F("device__name")).annotate(count=Count("id")).order_by("-count")[:8]),default=str)}
    return render(request,"pms/dashboard.html",context)
@login_required
def complaint_list(request):
    qs=visible_complaints(request.user); q=request.GET.get("q",""); status=request.GET.get("status","")
    if q: qs=qs.filter(title__icontains=q)
    if status: qs=qs.filter(status=status)
    return render(request,"pms/complaint_list.html",{"items":qs[:100],"statuses":CustomerComplaint.Status.choices})
@login_required
def complaint_create(request):
    form=ComplaintForm(request.POST or None)
    if form.is_valid(): obj=form.save(commit=False); obj.reporter=request.user; obj.save(); audit(request.user,"CREATE",obj,after={"title":obj.title}); return redirect("complaint-detail",obj.pk)
    return render(request,"pms/form.html",{"form":form,"title":"고객 불만 접수"})
@login_required
def complaint_detail(request,pk):
    obj=get_object_or_404(visible_complaints(request.user),pk=pk); return render(request,"pms/complaint_detail.html",{"item":obj,"warnings":recurrent_warning(obj),"next_status":__import__("pms.services",fromlist=["TRANSITIONS"]).TRANSITIONS.get(obj.status)})
@login_required
@require_POST
def complaint_transition(request,pk):
    obj=get_object_or_404(visible_complaints(request.user),pk=pk); transition_complaint(obj,request.POST.get("status"),request.user,request.META.get("REMOTE_ADDR")); return redirect("complaint-detail",pk)
@login_required
def device_list(request): return render(request,"pms/object_list.html",{"title":"의료기기","items":MedicalDevice.objects.select_related("manufacturer"),"headers":["제품명","모델","제조사"]})
@login_required
def lot_list(request): return render(request,"pms/lot_list.html",{"items":ProductLot.objects.select_related("device","udi")})
@login_required
@raqa_required
def adverse_list(request): return render(request,"pms/adverse_list.html",{"items":AdverseEvent.objects.select_related("complaint")})
@login_required
@raqa_required
def capa_list(request): return render(request,"pms/capa_list.html",{"items":CAPA.objects.select_related("complaint","owner")})
@login_required
@raqa_required
def recall_list(request): return render(request,"pms/recall_list.html",{"items":Recall.objects.select_related("device")})
@login_required
@raqa_required
def report_list(request): return render(request,"pms/report_list.html",{"items":RegulatoryReport.objects.select_related("complaint")})
@login_required
@raqa_required
def report_print(request,pk):
    obj=get_object_or_404(RegulatoryReport,pk=pk); audit(request.user,"REPORT_GENERATE",obj); return render(request,"pms/report_print.html",{"item":obj})
@login_required
def notifications(request): return render(request,"pms/notifications.html",{"items":Notification.objects.filter(user=request.user)})
@login_required
def approvals(request):
    if role(request.user)!=Profile.Role.ADMIN: raise PermissionDenied
    return render(request,"pms/approvals.html",{"items":Approval.objects.filter(decision="PENDING")})
@login_required
def audit_logs(request):
    if role(request.user)!=Profile.Role.ADMIN: raise PermissionDenied
    return render(request,"pms/audits.html",{"items":AuditLog.objects.select_related("actor")[:200]})
@login_required
def users(request):
    if role(request.user)!=Profile.Role.ADMIN: raise PermissionDenied
    return render(request,"pms/users.html",{"items":Profile.objects.select_related("user")})
@login_required
def attachment_download(request,pk):
    obj=get_object_or_404(Attachment,pk=pk,complaint__in=visible_complaints(request.user)); audit(request.user,"ATTACHMENT_DOWNLOAD",obj); return FileResponse(obj.file.open("rb"),as_attachment=True,filename=obj.original_name or "attachment")
@login_required
@require_POST
def attachment_upload(request,pk):
    complaint=get_object_or_404(visible_complaints(request.user),pk=pk); form=AttachmentForm(request.POST,request.FILES)
    if not form.is_valid(): raise ValidationError(form.errors.as_json())
    obj=form.save(commit=False); obj.complaint=complaint; obj.uploaded_by=request.user; obj.original_name=Path(obj.file.name).name; obj.full_clean(); obj.save(); audit(request.user,"CREATE",obj,after={"original_name":obj.original_name}); return redirect("complaint-detail",pk)
