import json
from pathlib import Path
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import AdverseEventForm, AttachmentForm, CAPAForm, ComplaintForm, DeviceForm, LotForm, RecallForm, ReportForm, RiskForm
from .models import *
from .services import audit, decide_approval, recurrent_warning, request_complaint_approval, role, transition_complaint, visible_complaints
def raqa_required(view): return user_passes_test(lambda u: u.is_authenticated and role(u) in (Profile.Role.RA_QA,Profile.Role.ADMIN))(view)
@login_required
def dashboard(request):
    qs=visible_complaints(request.user); risks=RiskAssessment.objects.filter(complaint__in=qs); recalls=Recall.objects.exclude(progress_status="CLOSED")
    monthly=[{"month":x["month"].strftime("%Y-%m"),"count":x["count"]} for x in qs.annotate(month=TruncMonth("reported_on")).values("month").annotate(count=Count("id")).order_by("month")]
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
    if form.is_valid(): obj=form.save(commit=False); obj.reporter=request.user; obj.save(); audit(request.user,"CREATE",obj,after={"title":obj.title}); return redirect("complaint-workspace",obj.pk)
    return render(request,"pms/form.html",{"form":form,"title":"고객 불만 접수"})
@login_required
def complaint_detail(request,pk):
    obj=get_object_or_404(visible_complaints(request.user),pk=pk); privileged=role(request.user) in (Profile.Role.RA_QA,Profile.Role.ADMIN)
    approval=Approval.objects.filter(content_type="CustomerComplaint",object_id=obj.pk).order_by("-created_at").first()
    context={"item":obj,"warnings":recurrent_warning(obj),"next_status":__import__("pms.services",fromlist=["TRANSITIONS"]).TRANSITIONS.get(obj.status),"privileged":privileged,"is_admin":role(request.user)==Profile.Role.ADMIN,"risk_form":RiskForm(initial={"complaint":obj}),"capa_form":CAPAForm(),"report_form":ReportForm(),"recall_form":RecallForm(initial={"risk_level":getattr(getattr(obj,"risk_assessment",None),"level","")}),"approval":approval}
    return render(request,"pms/complaint_detail.html",context)
@login_required
@require_POST
def complaint_transition(request,pk):
    obj=get_object_or_404(visible_complaints(request.user),pk=pk)
    try: transition_complaint(obj,request.POST.get("status"),request.user,request.META.get("REMOTE_ADDR")); messages.success(request,"다음 업무 단계로 이동했습니다.")
    except ValidationError as exc: messages.error(request," ".join(exc.messages))
    return redirect("complaint-workspace",pk)
@login_required
@raqa_required
@require_POST
def risk_save(request,pk):
    complaint=get_object_or_404(CustomerComplaint,pk=pk); current=getattr(complaint,"risk_assessment",None); form=RiskForm(request.POST,instance=current)
    if form.is_valid(): obj=form.save(commit=False); obj.complaint=complaint; obj.assessed_by=request.user; obj.save(); audit(request.user,"UPDATE" if current else "CREATE",obj,after={"score":obj.score,"level":obj.level}); messages.success(request,f"위험평가 {obj.score}점({obj.level})을 저장했습니다.")
    else: messages.error(request,form.errors.as_text())
    return redirect("complaint-workspace",pk)
@login_required
@raqa_required
@require_POST
def capa_create(request,pk):
    complaint=get_object_or_404(CustomerComplaint,pk=pk); form=CAPAForm(request.POST)
    if form.is_valid(): obj=form.save(commit=False); obj.complaint=complaint; obj.save(); audit(request.user,"CREATE",obj,after={"title":obj.title}); messages.success(request,"CAPA를 생성했습니다.")
    else: messages.error(request,form.errors.as_text())
    return redirect("complaint-workspace",pk)
@login_required
@raqa_required
@require_POST
def report_create(request,pk):
    complaint=get_object_or_404(CustomerComplaint,pk=pk); existing=complaint.reports.order_by("-created_at").first(); form=ReportForm(request.POST,instance=existing)
    if form.is_valid():
        obj=form.save(commit=False); obj.complaint=complaint; obj.author=request.user; obj.document_number=obj.document_number or f"DEMO-RR-{timezone.now():%Y%m%d}-{complaint.pk:05d}"; obj.checklist={k:form.cleaned_data[k] for k in ("serious_event","health_deterioration","recurrence_possible","deadline_reviewed")}; obj.save(); audit(request.user,"REPORT_CREATE",obj,after=obj.checklist); messages.success(request,"규제보고 판단과 체크리스트를 저장했습니다.")
    else: messages.error(request,form.errors.as_text())
    return redirect("complaint-workspace",pk)
@login_required
@raqa_required
@require_POST
def recall_create(request,pk):
    complaint=get_object_or_404(CustomerComplaint,pk=pk); form=RecallForm(request.POST)
    if form.is_valid(): obj=form.save(commit=False); obj.complaint=complaint; obj.device=complaint.device; obj.owner=request.user; obj.full_clean(); obj.save(); audit(request.user,"CREATE",obj,after={"target_quantity":obj.target_quantity}); messages.success(request,"리콜 검토안을 생성했습니다.")
    else: messages.error(request,form.errors.as_text())
    return redirect("complaint-workspace",pk)
@login_required
@raqa_required
@require_POST
def approval_request(request,pk):
    complaint=get_object_or_404(CustomerComplaint,pk=pk)
    try: request_complaint_approval(complaint,request.user,request.META.get("REMOTE_ADDR")); messages.success(request,"관리자 승인을 요청했습니다.")
    except ValidationError as exc: messages.error(request," ".join(exc.messages))
    return redirect("complaint-workspace",pk)
@login_required
@require_POST
def approval_decide(request,pk,approval_pk):
    if role(request.user)!=Profile.Role.ADMIN: raise PermissionDenied
    approval=get_object_or_404(Approval,pk=approval_pk,content_type="CustomerComplaint",object_id=pk)
    try: decide_approval(approval,request.user,request.POST.get("decision"),request.POST.get("reason",""),request.META.get("REMOTE_ADDR")); messages.success(request,"승인 결정을 저장했습니다.")
    except ValidationError as exc: messages.error(request," ".join(exc.messages))
    return redirect("complaint-workspace",pk)
@login_required
def device_list(request): return render(request,"pms/object_list.html",{"title":"의료기기","items":MedicalDevice.objects.select_related("manufacturer"),"headers":["제품명","모델","제조사"]})
@login_required
def device_detail(request,pk): return render(request,"pms/device_detail.html",{"item":get_object_or_404(MedicalDevice.objects.select_related("manufacturer"),pk=pk)})
@login_required
@raqa_required
def device_create(request):
    form=DeviceForm(request.POST or None)
    if form.is_valid(): obj=form.save(); audit(request.user,"CREATE",obj,after={"model_number":obj.model_number}); return redirect("device-detail",obj.pk)
    return render(request,"pms/form.html",{"form":form,"title":"의료기기 등록"})
@login_required
def lot_list(request): return render(request,"pms/lot_list.html",{"items":ProductLot.objects.select_related("device","udi")})
@login_required
def lot_detail(request,pk): return render(request,"pms/lot_detail.html",{"item":get_object_or_404(ProductLot.objects.select_related("device","udi"),pk=pk)})
@login_required
@raqa_required
def lot_create(request):
    form=LotForm(request.POST or None)
    if form.is_valid(): obj=form.save(); audit(request.user,"CREATE",obj,after={"lot_number":obj.lot_number}); return redirect("lot-detail",obj.pk)
    return render(request,"pms/form.html",{"form":form,"title":"UDI·LOT·시리얼 등록"})
@login_required
def adverse_list(request): return render(request,"pms/adverse_list.html",{"items":AdverseEvent.objects.filter(complaint__in=visible_complaints(request.user)).select_related("complaint")})
@login_required
def adverse_create(request):
    form=AdverseEventForm(request.POST or None); form.fields["complaint"].queryset=visible_complaints(request.user)
    if role(request.user)==Profile.Role.STAFF: form.fields["patient"].queryset=PatientAnonymousInfo.objects.filter(complaint__reporter=request.user)
    if form.is_valid(): obj=form.save(); audit(request.user,"CREATE",obj,after={"event_type":obj.event_type}); return redirect("adverse-detail",obj.pk)
    return render(request,"pms/form.html",{"form":form,"title":"이상사례 등록"})
@login_required
def adverse_detail(request,pk): return render(request,"pms/adverse_detail.html",{"item":get_object_or_404(AdverseEvent.objects.filter(complaint__in=visible_complaints(request.user)).select_related("complaint","patient"),pk=pk)})
@login_required
@raqa_required
def capa_list(request): return render(request,"pms/capa_list.html",{"items":CAPA.objects.select_related("complaint","owner")})
@login_required
@raqa_required
def capa_detail(request,pk): return render(request,"pms/capa_detail.html",{"item":get_object_or_404(CAPA.objects.select_related("complaint","owner"),pk=pk)})
@login_required
@raqa_required
def recall_list(request): return render(request,"pms/recall_list.html",{"items":Recall.objects.select_related("device")})
@login_required
@raqa_required
def recall_detail(request,pk): return render(request,"pms/recall_detail.html",{"item":get_object_or_404(Recall.objects.select_related("device","owner","complaint"),pk=pk)})
@login_required
@require_POST
def recall_admin_action(request,pk):
    if role(request.user)!=Profile.Role.ADMIN: raise PermissionDenied
    obj=get_object_or_404(Recall,pk=pk); action=request.POST.get("action")
    before={"approval_status":obj.approval_status,"progress_status":obj.progress_status}
    reason=request.POST.get("decision_reason","").strip()
    if action=="approve": obj.approval_status=Recall.Approval.APPROVED; obj.decision_reason=reason
    elif action=="reject":
        if not reason: messages.error(request,"리콜 반려 사유는 필수입니다."); return redirect("recall-detail",pk)
        obj.approval_status=Recall.Approval.REJECTED; obj.decision_reason=reason
    elif action=="close":
        obj.closure_report=request.POST.get("closure_report",obj.closure_report).strip()
        if obj.approval_status!=Recall.Approval.APPROVED or not obj.closure_report.strip(): messages.error(request,"승인과 종료 보고서가 있어야 리콜을 종료할 수 있습니다."); return redirect("recall-detail",pk)
        obj.progress_status=Recall.Progress.CLOSED
    else: raise ValidationError("지원하지 않는 리콜 조치입니다.")
    obj.save(); audit(request.user,"RECALL_"+action.upper(),obj,before,{"approval_status":obj.approval_status,"progress_status":obj.progress_status}); messages.success(request,"리콜 상태를 변경했습니다."); return redirect("recall-detail",pk)
@login_required
@raqa_required
def recall_print(request,pk):
    obj=get_object_or_404(Recall.objects.select_related("device","owner","complaint"),pk=pk); audit(request.user,"REPORT_GENERATE",obj); return render(request,"pms/recall_print.html",{"item":obj})
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
@require_POST
def user_update(request,pk):
    if role(request.user)!=Profile.Role.ADMIN: raise PermissionDenied
    profile=get_object_or_404(Profile.objects.select_related("user"),pk=pk); before={"role":profile.role,"active":profile.user.is_active}; requested=request.POST.get("role")
    if requested not in Profile.Role.values: messages.error(request,"올바르지 않은 역할입니다."); return redirect("user-list")
    if profile.user_id==request.user.id and (requested!=Profile.Role.ADMIN or request.POST.get("is_active")!="on"): messages.error(request,"현재 관리자 자신의 ADMIN 권한이나 활성 상태는 해제할 수 없습니다."); return redirect("user-list")
    profile.role=requested; profile.save(update_fields=["role"]); profile.user.is_active=request.POST.get("is_active")=="on"; profile.user.save(update_fields=["is_active"]); audit(request.user,"UPDATE",profile,before,{"role":profile.role,"active":profile.user.is_active}); messages.success(request,"사용자 권한을 변경했습니다."); return redirect("user-list")
@login_required
def attachment_download(request,pk):
    obj=get_object_or_404(Attachment,pk=pk,complaint__in=visible_complaints(request.user)); audit(request.user,"ATTACHMENT_DOWNLOAD",obj); return FileResponse(obj.file.open("rb"),as_attachment=True,filename=obj.original_name or "attachment")
@login_required
@require_POST
def attachment_upload(request,pk):
    complaint=get_object_or_404(visible_complaints(request.user),pk=pk); form=AttachmentForm(request.POST,request.FILES)
    if not form.is_valid(): raise ValidationError(form.errors.as_json())
    obj=form.save(commit=False); obj.complaint=complaint; obj.uploaded_by=request.user; obj.original_name=Path(obj.file.name).name; obj.full_clean(); obj.save(); audit(request.user,"CREATE",obj,after={"original_name":obj.original_name}); return redirect("complaint-workspace",pk)
