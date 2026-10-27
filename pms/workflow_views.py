from datetime import timedelta
import hashlib
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import *
from .services import role, visible_complaints, audit
from .workflow import *
from .workflow_forms import *
from .reporting import generate_report
from .file_security import safe_attachment_bytes, private_path


def form_page(request,form,title): return render(request,"pms/form.html",{"form":form,"title":title})

@login_required
def task_list(request):
    qs=tasks_for(request.user)
    if request.GET.get("all")!="1": qs=qs.filter(assignee=request.user)
    now=timezone.now(); kind=request.GET.get("filter")
    if kind=="soon": qs=qs.filter(due_at__gte=now,due_at__lte=now+timedelta(days=settings.TASK_DUE_SOON_DAYS)).exclude(status="DONE")
    if kind=="overdue": qs=qs.filter(due_at__lt=now).exclude(status="DONE")
    return render(request,"pms/task_list.html",{"items":qs,"days":settings.TASK_DUE_SOON_DAYS})

@login_required
def task_edit(request,pk=None):
    obj=get_object_or_404(tasks_for(request.user),pk=pk) if pk else WorkTask()
    if not pk: privileged(request.user)
    form=TaskForm(request.POST or None,instance=obj,initial={k:request.GET[k] for k in ("complaint","capa","recall") if k in request.GET})
    if role(request.user)=="STAFF":
        for name,field in form.fields.items():
            if name!="status": field.disabled=True
    if request.method=="POST" and form.is_valid():
        try: save_task(form.save(commit=False),request.user); return redirect("task-detail",pk=form.instance.pk)
        except ValidationError as exc: form.add_error(None,exc)
    return form_page(request,form,"담당 업무 수정" if pk else "담당 업무 등록")

@login_required
def task_detail(request,pk):
    obj=get_object_or_404(tasks_for(request.user),pk=pk)
    return render(request,"pms/task_detail.html",{"item":obj})

@login_required
def capa_evaluate(request,pk):
    privileged(request.user); obj=get_object_or_404(CAPA,pk=pk)
    form=EvaluationForm(request.POST or None,initial={"action_result":obj.action_result,"criteria":obj.evaluation_criteria,"scheduled_on":obj.evaluation_due,"evaluated_on":timezone.localdate()})
    form.fields["evidence"].queryset=Attachment.objects.filter(complaint=obj.complaint,scan_status="PASSED")
    if request.method=="POST" and form.is_valid():
        try: evaluate_capa(obj,request.user,form.cleaned_data,form.cleaned_data["evidence"]); return redirect("capa-detail",pk)
        except ValidationError as exc: form.add_error(None,exc)
    return form_page(request,form,"CAPA 효과성 평가 (이력 추가)")

@login_required
@require_POST
def capa_close(request,pk):
    obj=get_object_or_404(CAPA,pk=pk)
    try: close_capa(obj,request.user); messages.success(request,"CAPA를 종결했습니다.")
    except ValidationError as exc: messages.error(request," ".join(exc.messages))
    return redirect("capa-detail",pk)

@login_required
def recipient_edit(request,recall_pk,pk=None):
    privileged(request.user); recall=get_object_or_404(Recall,pk=recall_pk)
    obj=get_object_or_404(RecallRecipient,pk=pk,recall=recall) if pk else RecallRecipient(recall=recall)
    form=RecipientForm(request.POST or None,instance=obj)
    form.fields["lot"].queryset=ProductLot.objects.filter(device=recall.device)
    if pk:
        for name in ("lot","partner","unit","target_quantity"): form.fields[name].disabled=True
    if request.method=="POST" and form.is_valid():
        try: save_recipient(form.save(commit=False),request.user); return redirect("recall-ledger",recall_pk)
        except ValidationError as exc: form.add_error(None,exc)
    return form_page(request,form,"거래처별 회수 대상·통보·회신")

@login_required
def partner_create(request):
    privileged(request.user); form=PartnerForm(request.POST or None)
    if request.method=="POST" and form.is_valid(): obj=form.save(); audit(request.user,"PARTNER_CREATE",obj); return redirect("recall-list")
    return form_page(request,form,"거래처 등록")

@login_required
def recall_ledger(request,pk):
    privileged(request.user); obj=get_object_or_404(Recall,pk=pk)
    return render(request,"pms/recall_ledger.html",{"item":obj,"totals":recall_totals(obj)})

@login_required
def recovery_create(request,pk):
    privileged(request.user); obj=get_object_or_404(RecallRecipient,pk=pk)
    form=RecoveryForm(request.POST or None,initial={"recovered_on":timezone.localdate()})
    if request.method=="POST" and form.is_valid():
        try: record_recovery(obj,request.user,**form.cleaned_data); return redirect("recall-ledger",obj.recall_id)
        except ValidationError as exc: form.add_error(None,exc)
    return form_page(request,form,f"부분 회수 등록 · 단위 {obj.unit} · 잔여 {obj.remaining_quantity}")

@login_required
def contact_create(request,pk):
    privileged(request.user); obj=get_object_or_404(RecallRecipient,pk=pk); form=ContactForm(request.POST or None,initial={"contacted_at":timezone.localtime()})
    if request.method=="POST" and form.is_valid():
        contact=form.save(commit=False); contact.recipient=obj
        record_contact(contact,request.user); return redirect("recall-ledger",obj.recall_id)
    return form_page(request,form,"거래처 후속 연락 이력 등록")

@login_required
def rule_list(request):
    if role(request.user)!="ADMIN": raise PermissionDenied
    return render(request,"pms/rule_list.html",{"items":ReportingRule.objects.order_by("name","-version")})

@login_required
def rule_create(request):
    if role(request.user)!="ADMIN": raise PermissionDenied
    form=RuleForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        try: create_rule(form.save(commit=False),request.user); return redirect("rule-list")
        except ValidationError as exc: form.add_error(None,exc)
    return form_page(request,form,"보고 규칙 새 버전 · 실제 법정 기준은 별도 검토")

@login_required
def rule_apply(request,pk):
    privileged(request.user); obj=get_object_or_404(CustomerComplaint,pk=pk); form=ApplyRuleForm(request.POST or None)
    names=ReportingRule.objects.filter(effective_on__lte=timezone.localdate()).values_list("name",flat=True).distinct()
    form.fields["name"].choices=[(name,name) for name in names]
    if request.method=="POST" and form.is_valid():
        try: apply_rule(obj,request.user,**form.cleaned_data); return redirect("complaint-workspace",pk)
        except ValidationError as exc: form.add_error(None,exc)
    return form_page(request,form,"사건 보고 규칙 적용·재적용 (기존 이력 보존)")

@login_required
def artifact_list(request,pk):
    privileged(request.user); obj=get_object_or_404(visible_complaints(request.user),pk=pk)
    return render(request,"pms/artifact_list.html",{"item":obj})

@login_required
@require_POST
def artifact_generate(request,pk):
    privileged(request.user); obj=get_object_or_404(visible_complaints(request.user),pk=pk)
    try: generate_report(obj,request.user); messages.success(request,"새 PDF 버전을 생성했습니다.")
    except (ValidationError,ValueError) as exc: messages.error(request,str(exc))
    return redirect("artifact-list",pk)

@login_required
def artifact_download(request,pk,bundle=False):
    privileged(request.user)
    obj=get_object_or_404(ReportArtifact,pk=pk,complaint__in=visible_complaints(request.user))
    # A preserved report must not become an escape hatch after evidence is quarantined.
    for reference in obj.snapshot.get("evidence",[]):
        if reference.get("scan_status")=="PASSED":
            attachment=get_object_or_404(Attachment,pk=reference["id"],complaint=obj.complaint)
            if attachment.sha256!=reference.get("sha256"): raise PermissionDenied("생성 당시 증빙과 현재 증빙이 다릅니다.")
            safe_attachment_bytes(attachment)
    file=obj.bundle if bundle else obj.file; expected=obj.bundle_sha256 if bundle else obj.sha256
    stream=private_path(file).open("rb")
    if hashlib.file_digest(stream,"sha256").hexdigest()!=expected: stream.close(); raise PermissionDenied("보고서 무결성 검사 실패")
    stream.seek(0); audit(request.user,"PDF_DOWNLOAD",obj,after={"bundle":bundle})
    return FileResponse(stream,as_attachment=True,filename=f"{obj.number}-v{obj.version}.{'zip' if bundle else 'pdf'}")
