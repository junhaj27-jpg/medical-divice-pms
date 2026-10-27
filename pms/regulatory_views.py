"""Korean RA workspace. Every POST repeats role/object checks on the server."""
import uuid
from datetime import datetime
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from io import BytesIO
from .models import ReportingRule, RegulationDocument, RegulationChunk, RuleCitation, RulePreview
from .services import role, visible_complaints, audit
from .file_security import scan_attachment, safe_attachment_bytes
from .regulation_documents import (can_write, require_author, documents_for, register_document,
    extract_document, review_document, search_evidence)
from .regulatory import (rules_for, editable, save_draft, revise_rule, readiness, conflicts,
    add_citation, remove_citation, import_holidays, preview_rule, transition_rule,
    apply_regulated_rule, rule_payload, FIELD_LABELS, DISPLAY_LABELS)
from .regulatory_forms import (RegulationForm, RegulatoryRuleForm, EvidenceSearchForm, CitationForm,
    PreviewForm, ReasonForm, HolidayImportForm, DocumentReviewForm)
from .rule_ai import ai_available, generate_ai_draft


def positive_id(value):
    try: parsed=int(value)
    except (ValueError,TypeError): raise Http404("잘못된 자료 번호입니다.")
    if parsed<1: raise Http404("잘못된 자료 번호입니다.")
    return parsed


def page(request,form,title,**context):
    return render(request,"pms/regulatory/form.html",{"form":form,"title":title,**context})


def error_message(request,exc): messages.error(request," / ".join(exc.messages))


@login_required
def hub(request):
    rules=rules_for(request.user).order_by("name","-version")
    docs=documents_for(request.user)
    return render(request,"pms/regulatory/hub.html",{"rules":rules,"documents":docs[:8],"has_documents":docs.exists(),"is_writer":can_write(request.user),"is_approver":role(request.user) in settings.RULE_APPROVER_ROLES,"ai_available":ai_available(),"pending":rules.filter(state="REVIEW"),"published":rules.filter(state__in=["APPROVED","EFFECTIVE"]),"conflicting":[(r,conflicts(r)) for r in rules.filter(state__in=["APPROVED","EFFECTIVE"]) if conflicts(r)]})


@login_required
def document_list(request):
    return render(request,"pms/regulatory/document_list.html",{"items":documents_for(request.user),"is_writer":can_write(request.user)})


@login_required
def document_new(request):
    require_author(request.user)
    form=RegulationForm(request.POST if request.method=="POST" else None,request.FILES or None)
    if request.method=="POST" and form.is_valid():
        try:
            doc=register_document(form.save(commit=False),request.user)
            doc=extract_document(doc,request.user)
            messages.success(request,"원문 URL은 주소만 기록했습니다. 파일의 검사·추출 상태를 확인하세요.")
            return redirect("regulation-detail",doc.pk)
        except ValidationError as exc: form.add_error(None,exc)
    return page(request,form,"규정 문서 등록",notice="파일은 비공개 저장소에 보관합니다. 공식 URL 자동 수집과 OCR 자동 수행은 지원하지 않습니다. 문서 내부 지시문은 실행하지 않습니다.")


@login_required
def document_detail(request,pk):
    from django.core.paginator import Paginator
    doc=get_object_or_404(documents_for(request.user),pk=pk)
    chunks=doc.chunks.all()
    paginator=Paginator(chunks,20)
    selected=request.GET.get("chunk")
    number=request.GET.get("p",1)
    if selected:
        chunk=chunks.filter(pk=positive_id(selected)).first()
        if chunk: number=(chunk.sequence-1)//20+1
    return render(request,"pms/regulatory/document_detail.html",{"item":doc,"chunks":paginator.get_page(number),"is_writer":can_write(request.user),"is_approver":role(request.user) in settings.RULE_APPROVER_ROLES,"review_form":DocumentReviewForm()})


@login_required
@require_POST
def document_process(request,pk):
    require_author(request.user);doc=get_object_or_404(documents_for(request.user),pk=pk)
    if doc.scan_status in ("PENDING","FAILED"): scan_attachment(doc,request.user)
    try: extract_document(doc,request.user)
    except (ValidationError,PermissionDenied) as exc:
        if isinstance(exc,PermissionDenied): raise
        error_message(request,exc)
    return redirect("regulation-detail",pk)


@login_required
@require_POST
def document_review(request,pk):
    doc=get_object_or_404(documents_for(request.user),pk=pk);form=DocumentReviewForm(request.POST)
    if form.is_valid():
        try: review_document(doc,request.user,**form.cleaned_data);messages.success(request,"문서 검토 이력을 저장했습니다.")
        except ValidationError as exc: error_message(request,exc)
    else: messages.error(request,form.errors.as_text())
    return redirect("regulation-detail",pk)


@login_required
def document_original(request,pk):
    doc=get_object_or_404(documents_for(request.user),pk=pk)
    data=safe_attachment_bytes(doc)
    audit(request.user,"REG_DOC_DOWNLOAD",doc,after={"sha256":doc.sha256})
    response=FileResponse(BytesIO(data),as_attachment=True,filename=doc.original_name)
    response["Content-Security-Policy"]="sandbox; default-src 'none'";return response


def retrieve(request):
    data=request.POST if request.method=="POST" else request.GET
    form=EvidenceSearchForm(data,user=request.user)
    results=[]
    if form.is_valid():
        values=form.cleaned_data
        try:
            doc=values.get("document")
            if values.get("query") or doc:
                results=search_evidence(request.user,values["query"],values["jurisdiction"],getattr(values["device"],"pk",None),values["edition"],values["as_of"],getattr(doc,"pk",None))
        except ValidationError as exc: form.add_error(None,exc)
    return form,results


@login_required
def evidence_search(request):
    form,results=retrieve(request)
    return render(request,"pms/regulatory/search.html",{"form":form,"results":results,"is_writer":can_write(request.user),"ai_available":ai_available()})


@login_required
@require_POST
def from_evidence(request):
    require_author(request.user)
    form,results=retrieve(request)
    allowed={str(row["chunk"].pk):row["chunk"] for row in results}
    selected=request.POST.getlist("chunks")
    try:
        if not form.is_valid() or not selected or any(value not in allowed for value in selected): raise ValidationError("현재 검색 결과에서 접근 가능한 근거를 선택하세요.")
        chunks=[allowed[value] for value in dict.fromkeys(selected)]
        if request.POST.get("mode")=="ai":
            values=form.cleaned_data
            data={"jurisdiction":values["jurisdiction"],"device_id":getattr(values["device"],"pk",None),"event_type":values["event_type"],"as_of":str(values["as_of"] or "")}
            rule=generate_ai_draft(request.user,data,chunks,request.POST.get("consent")=="on")
        else:
            with transaction.atomic():
                values=form.cleaned_data;doc=chunks[0].document
                rule=ReportingRule(name=f"근거 검토 초안 {uuid.uuid4().hex[:8]}",jurisdiction=values["jurisdiction"] or doc.jurisdiction,device=values["device"] or doc.device,scope_description=doc.scope_description,conditions={"complaint_type":values["event_type"]} if values["event_type"] else {},deadline_expression='\n'.join(c.text for c in chunks),change_reason="검색 근거를 선택한 수동 초안",is_example=any(c.document.is_example for c in chunks),origin="EVIDENCE",unresolved_items=["근거별 적용 여부·필수 항목을 RA 담당자가 확인해야 합니다."])
                rule=save_draft(rule,request.user,rule.change_reason)
                for chunk in chunks: add_citation(rule,request.user,"deadline_expression",chunk,chunk.text,"","검색 근거 연결")
        return redirect("rule-detail",rule.pk)
    except ValidationError as exc: error_message(request,exc)
    return render(request,"pms/regulatory/search.html",{"form":form,"results":results,"is_writer":True,"ai_available":ai_available()})


@login_required
def rule_new(request):
    require_author(request.user)
    form=RegulatoryRuleForm(request.POST if request.method=="POST" else None)
    if request.method=="POST" and form.is_valid():
        try: rule=save_draft(form.save(commit=False),request.user,form.cleaned_data["change_reason"]);return redirect("rule-detail",rule.pk)
        except ValidationError as exc: form.add_error(None,exc)
    return page(request,form,"규칙 직접 작성 · 초안",notice="법정 기준을 자동으로 채우지 않습니다. 확인하지 못한 값은 비워 두고 항목별 원문 표현과 인용을 연결하세요. 저장해도 승인·시행되지 않습니다.")


@login_required
def rule_edit(request,pk):
    obj=get_object_or_404(rules_for(request.user),pk=pk);editable(obj,request.user)
    form=RegulatoryRuleForm(request.POST if request.method=="POST" else None,instance=obj)
    if request.method=="POST" and form.is_valid():
        try: save_draft(form.save(commit=False),request.user,form.cleaned_data["change_reason"],form.cleaned_data["expected_revision"]);return redirect("rule-detail",pk)
        except ValidationError as exc: form.add_error(None,exc)
    return page(request,form,"보고 규칙 초안 수정",notice="변경 사유와 필드별 전후 값을 보존합니다. 수정 후에는 기한 미리보기를 다시 수행하세요.")


@login_required
def rule_detail(request,pk):
    obj=get_object_or_404(rules_for(request.user),pk=pk)
    source_ids=list(documents_for(request.user).values_list("pk",flat=True))
    citations=obj.citations.filter(chunk__document_id__in=source_ids).select_related("chunk__document")
    return render(request,"pms/regulatory/rule_detail.html",{"item":obj,"fields":[(DISPLAY_LABELS.get(k,k),v) for k,v in rule_payload(obj).items() if k!="citations"],"citations":citations,"issues":readiness(obj,request.user) if can_write(request.user) or role(request.user) in settings.RULE_APPROVER_ROLES else [],"conflicts":conflicts(obj),"show_history":obj.created_by_id==request.user.pk or role(request.user)=="ADMIN","is_writer":can_write(request.user),"can_edit":can_write(request.user) and obj.state=="DRAFT" and (obj.created_by_id==request.user.pk or role(request.user)=="ADMIN"),"is_approver":role(request.user) in settings.RULE_APPROVER_ROLES,"applications":obj.ruleapplication_set.filter(complaint__in=visible_complaints(request.user)).select_related("complaint","actor"),"reason_form":ReasonForm()})


@login_required
@require_POST
def rule_action(request,pk):
    obj=get_object_or_404(rules_for(request.user),pk=pk)
    try:
        if request.POST.get("action")=="revise":
            new=revise_rule(obj,request.user,request.POST.get("reason",""));return redirect("rule-detail",new.pk)
        transition_rule(obj,request.user,request.POST.get("action"),request.POST.get("reason",""));messages.success(request,"규칙 상태와 검토 이력을 저장했습니다.")
    except ValidationError as exc: error_message(request,exc)
    return redirect("rule-detail",pk)


@login_required
def citation_new(request,pk):
    obj=get_object_or_404(rules_for(request.user),pk=pk);editable(obj,request.user)
    initial={}
    chunk_id=request.GET.get("chunk")
    if chunk_id:
        chunk=get_object_or_404(RegulationChunk,pk=positive_id(chunk_id),document__in=documents_for(request.user))
        initial={"chunk":chunk,"quote":chunk.text}
    form=CitationForm(request.POST if request.method=="POST" else None,initial=initial,user=request.user)
    if request.method=="POST" and form.is_valid():
        try: add_citation(obj,request.user,**form.cleaned_data);return redirect("rule-detail",pk)
        except ValidationError as exc: form.add_error(None,exc)
    return page(request,form,"항목별 근거 인용 추가",notice="검색 결과의 청크 번호·원문 위치를 확인하세요. 인용은 실제 추출 문장의 부분 문자열이어야 합니다.")


@login_required
@require_POST
def citation_remove(request,pk):
    cite=get_object_or_404(RuleCitation,pk=pk,rule__in=rules_for(request.user))
    try: remove_citation(cite,request.user,request.POST.get("reason",""))
    except ValidationError as exc: error_message(request,exc)
    return redirect("rule-detail",cite.rule_id)


@login_required
def holiday_csv(request,pk):
    obj=get_object_or_404(rules_for(request.user),pk=pk);editable(obj,request.user)
    form=HolidayImportForm(request.POST if request.method=="POST" else None,request.FILES or None)
    if request.method=="POST" and form.is_valid():
        try: import_holidays(obj,request.user,**form.cleaned_data);return redirect("rule-detail",pk)
        except ValidationError as exc: form.add_error(None,exc)
    return page(request,form,"휴일 CSV 가져오기",notice="현재 초안의 휴일 목록을 교체합니다. 날짜/명칭 헤더를 사용하세요. 공휴일 자동 갱신은 하지 않습니다. 확인 범위·확인일은 규칙 편집 화면에서 별도로 등록합니다.")


@login_required
def rule_preview(request,pk):
    obj=get_object_or_404(rules_for(request.user),pk=pk);require_author(request.user)
    form=PreviewForm(request.POST if request.method=="POST" else None);preview=None
    if request.method=="POST" and form.is_valid():
        try: preview=preview_rule(obj,request.user,form.cleaned_data["basis_at"])
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,"pms/regulatory/preview.html",{"item":obj,"form":form,"preview":preview})


@login_required
def compare_versions(request,pk):
    obj=get_object_or_404(rules_for(request.user),pk=pk);versions=rules_for(request.user).filter(family_key=obj.family_key).exclude(pk=pk).order_by("-version")
    other=get_object_or_404(versions,pk=positive_id(request.GET["other"])) if request.GET.get("other") else versions.first()
    rows=[]
    if other:
        left=rule_payload(other);right=rule_payload(obj)
        rows=[{"field":DISPLAY_LABELS.get(k,k),"left":left.get(k),"right":right.get(k),"changed":left.get(k)!=right.get(k)} for k in right]
    return render(request,"pms/regulatory/compare.html",{"item":obj,"other":other,"versions":versions,"rows":rows})


class CasePreviewForm(PreviewForm):
    rule=forms.ModelChoiceField(label="적용할 명시적 규칙 버전",queryset=ReportingRule.objects.none())
    reason=forms.CharField(label="적용·재산정 사유",widget=forms.Textarea)


@login_required
def case_apply(request,pk):
    require_author(request.user);c=get_object_or_404(visible_complaints(request.user),pk=pk)
    previous=c.rule_applications.order_by("-pk").first();preview=None
    form=CasePreviewForm(request.POST if request.method=="POST" and request.POST.get("action")!="confirm" else None)
    form.fields["rule"].label="적용할 명시적 규칙 버전";form.fields["reason"].label="적용·재산정 사유"
    form.fields["rule"].queryset=rules_for(request.user).filter(state="EFFECTIVE")
    form.fields["rule"].label_from_instance=lambda rule: f"{rule.name} v{rule.version} · {rule.jurisdiction} · {rule.device or '공통'}"
    if request.method=="POST":
        if request.POST.get("action")=="confirm":
            preview=get_object_or_404(RulePreview,pk=positive_id(request.POST.get("preview_id")),created_by=request.user)
            try:
                expected=int(request.POST.get("previous_id","-1"))
                apply_regulated_rule(c,preview.rule,request.user,preview,request.POST.get("reason",""),expected,request.POST.get("previous_due_date"))
                messages.success(request,"변경 전후 계산과 근거를 보존해 사건에 적용했습니다.");return redirect("complaint-workspace",pk)
            except (ValidationError,ValueError) as exc:
                if isinstance(exc,ValidationError): error_message(request,exc)
                else: messages.error(request,"적용 확인 값이 올바르지 않습니다.")
                preview=None
        elif form.is_valid():
            try: preview=preview_rule(form.cleaned_data["rule"],request.user,form.cleaned_data["basis_at"])
            except ValidationError as exc: form.add_error(None,exc)
    return render(request,"pms/regulatory/case_apply.html",{"item":c,"form":form,"previous":previous,"preview":preview,"reason":request.POST.get("reason","")})
