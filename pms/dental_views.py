import io
from datetime import date
import re

from django import forms
from django.db import transaction
from django.db.models import F
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from pypdf import PdfReader

from .dental_models import DentalDraft, DentalGuide, DentalProject
from .dental_workflow import (ESTAR, FEATURES, GUIDE, LAW, METRIC_UNITS, SECTIONS, STANDARDS, TEST_FIELDS,
                              build_snapshot, csv_export, docx_export, in_scope, stale_sections)
from .fda_510k_views import FDA_SEARCH, case_results
from .fda_classification import LookupError
from .file_security import safe_attachment_bytes
from .market_service import market_access
from .market_views import device_for, market_view
from .models import ControlledDocument
from .services import audit


class ProjectForm(forms.Form):
    product_name = forms.CharField(label="제품명", max_length=200)
    model = forms.CharField(label="모델", max_length=100)
    intended_use = forms.CharField(label="사용목적 (영문)", widget=forms.Textarea(attrs={"rows": 2}), max_length=1500)
    product_code = forms.CharField(label="제품 코드", max_length=10)
    regulation = forms.CharField(label="규정 번호", max_length=40)
    use_scope = forms.ChoiceField(label="범위", choices=[
        ("restorative", "치과 수복 레진 광중합"), ("bleaching", "미백 전용"), ("unknown", "불명확")])
    light_source = forms.ChoiceField(label="광원", choices=[
        ("broad_beam", "Broad beam"), ("monochromatic", "Monochromatic"), ("laser", "Laser"), ("unknown", "Unknown")])
    scope_confirmed = forms.BooleanField(label="RA가 사용목적과 EBZ 범위를 확인함", required=False)
    changed = forms.BooleanField(label="변경 제품", required=False)
    change_details = forms.CharField(label="변경 전후 모델·사양, 시험 영향, RA 판단 근거", required=False,
                                     max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))
    example = forms.BooleanField(label="예시 자료", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {"modes": "작동 모드", "contacts": "환자 접촉 부품", "power": "방사 파워 (mW)",
                  "irradiance": "방사조도 (mW/cm²)", "wavelength": "파장 (nm)", "exposure": "노출 시간 (s)",
                  "temperature": "온도 (°C)", "power_supply": "전원", "software": "소프트웨어", "wireless": "무선 기능"}
        for key, label in labels.items():
            self.fields[key] = forms.CharField(label=label, max_length=300, required=False)

    def clean_product_code(self):
        return self.cleaned_data["product_code"].upper()

    def clean_regulation(self):
        return self.cleaned_data["regulation"].upper().removeprefix("21 CFR ").strip()

    def clean(self):
        data = super().clean()
        if data.get("example") and not data.get("model", "").startswith("DEMO-"):
            self.add_error("model", "예시 모델 식별자는 DEMO-로 시작해야 합니다.")
        return data


class EvidenceForm(forms.Form):
    document = forms.ModelChoiceField(queryset=ControlledDocument.objects.none(), label="관리 문서 버전")
    section = forms.ChoiceField(label="가이드 절")
    page = forms.IntegerField(label="PDF 페이지 (텍스트 파일은 1)", min_value=1, max_value=10000)
    location = forms.CharField(label="페이지 내 표·항목", max_length=160, required=False)
    excerpt = forms.CharField(label="페이지에 있는 영문 발췌문", max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))
    model = forms.CharField(label="시험품 또는 자료 대상 모델", max_length=100)
    metric = forms.ChoiceField(label="측정량", required=False,
                               choices=[("", "—"), *((key, f"{key} ({unit})") for key, unit in METRIC_UNITS.items())])
    value = forms.CharField(label="원본 값", required=False, max_length=100)
    unit = forms.CharField(label="원본 단위", required=False, max_length=30)

    def __init__(self, *args, documents, sections, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["document"].queryset = documents
        self.fields["section"].choices = [(key, f"{key} {value[0]}") for key, value in sections.items()]
        for key, label in zip(TEST_FIELDS, ("시험 구성", "작동 모드", "시험 조건", "시험 방법", "허용 기준", "결과")):
            self.fields[key] = forms.CharField(label=label, max_length=400, required=False)

    def clean(self):
        data = super().clean()
        document, page, excerpt = (data.get(key) for key in ("document", "page", "excerpt"))
        if data.get("metric") and (not data.get("value") or not data.get("unit")):
            self.add_error("value", "측정값과 원본 단위를 함께 입력하세요.")
        if not (document and page and excerpt):
            return data
        try:
            raw = safe_attachment_bytes(document.primary_file)
            if raw.startswith(b"%PDF-"):
                text = PdfReader(io.BytesIO(raw)).pages[page - 1].extract_text() or ""
            elif page == 1 and document.primary_file.file.name.lower().endswith((".txt", ".csv")):
                text = raw.decode("utf-8-sig")
            else:
                text = ""
        except Exception:
            text = ""
        normalized = " ".join(text.split())
        if " ".join(excerpt.split()) not in normalized:
            self.add_error("excerpt", "검사 통과 문서의 지정 페이지에서 발췌문을 확인할 수 없습니다.")
        for key in ("model", "value", "unit", *TEST_FIELDS):
            if data.get(key) and not re.search(r"(?<![\w.])" + re.escape(" ".join(data[key].split())) + r"(?!\w)", normalized):
                self.add_error(key, "지정 페이지에서 이 값을 확인할 수 없습니다.")
        return data


def documents_for(device):
    return ControlledDocument.objects.filter(
        profile__device=device, profile__jurisdiction="US", primary_file__ra_profile_id=F("profile_id"),
        primary_file__scan_status="PASSED",
    ).select_related("primary_file").order_by("number", "-version")


def guide_for():
    DentalGuide.objects.get_or_create(issued_on=date.fromisoformat(GUIDE["issued_on"]), defaults={
        **{key: value for key, value in GUIDE.items() if key != "issued_on"}, "sections": SECTIONS,
    })
    return DentalGuide.objects.latest("issued_on")


def references_for(project, documents):
    docs = {doc.pk: doc for doc in documents}
    superseded = set(ControlledDocument.objects.filter(supersedes_id__in=docs).values_list("supersedes_id", flat=True))
    references = []
    for evidence in project.evidence.select_related("document__primary_file").order_by("pk"):
        doc = docs.get(evidence.document_id)
        if not doc:
            references.append({**dict.fromkeys(("model", "metric", "value", "unit", *TEST_FIELDS), ""),
                               "id": evidence.pk, "section": evidence.section,
                               "document_id": evidence.document_id, "identity": [],
                               "citation": "Unavailable evidence", "excerpt": "", "revised": True})
            continue
        details = evidence.details
        location = details["location"]
        references.append({**details, "id": evidence.pk, "section": evidence.section, "document_id": doc.pk,
                           "identity": [doc.revision, doc.primary_file_id, doc.primary_file.sha256],
                           "citation": f'{doc.number} v{doc.version} / p.{details["page"]}' + (f" / {location}" if location else ""),
                           "revised": doc.pk in superseded or details["identity"] != [doc.revision, doc.primary_file_id, doc.primary_file.sha256]})
    return references


@market_view
@never_cache
@require_http_methods(["GET", "POST"])
def workspace(request, pk):
    device = device_for(request, pk)
    if not market_access(request.user, ("US",), device):
        raise Http404
    if request.method == "POST":
        with transaction.atomic():
            device = device_for(request, pk, lock=True)
            if not market_access(request.user, ("US",), device):
                raise Http404
            return project_page(request, device)
    return project_page(request, device)


def project_page(request, device):
    project = DentalProject.objects.filter(device=device).select_related("guide").first()
    spec = project.specification if project else {}
    action = request.POST.get("action")
    form = ProjectForm(request.POST if action == "project" else None,
                       initial=spec or {"product_name": device.name, "model": device.model_number,
                                        "product_code": "EBZ", "regulation": "872.6070"})
    docs = documents_for(device)
    sections = project.guide.sections if project else SECTIONS
    evidence_form = EvidenceForm(request.POST if action == "evidence" else None, documents=docs,
                                 sections={key: value for key, value in sections.items() if key != "IV" or spec.get("changed")})
    error = ""
    if action == "project" and form.is_valid():
        updated = {**spec, **form.cleaned_data}
        DentalProject.objects.update_or_create(device=device, defaults={"guide": project.guide if project else guide_for(),
                                                                       "specification": updated})
        audit(request.user, "DENTAL_PROJECT", device)
        return redirect(request.path)
    if action and not project and action != "project":
        raise Http404
    if action == "guide":
        project.guide = guide_for()
        project.save(update_fields=["guide"])
        audit(request.user, "DENTAL_GUIDE_VERSION", project, after={"guide_id": project.guide_id})
        return redirect(request.path)
    if action == "evidence" and evidence_form.is_valid():
        data = evidence_form.cleaned_data.copy()
        doc, section = data.pop("document"), data.pop("section")
        data["identity"] = [doc.revision, doc.primary_file_id, doc.primary_file.sha256]
        event, created = project.evidence.get_or_create(document=doc, section=section, details=data)
        if created:
            audit(request.user, "DENTAL_EVIDENCE", event)
        return redirect(request.path)
    if action == "applicable" and request.POST.get("section") in sections:
        spec.get("not_applicable", {}).pop(request.POST["section"], None)
        project.save(update_fields=["specification"])
        audit(request.user, "DENTAL_APPLICABILITY", project, after={"section": request.POST["section"]})
        return redirect(request.path)
    if action == "na":
        section, reason = request.POST.get("section"), request.POST.get("rationale", "").strip()
        if section in sections and 0 < len(reason) <= 2000:
            spec.setdefault("not_applicable", {})[section] = reason
            project.save(update_fields=["specification"])
            audit(request.user, "DENTAL_APPLICABILITY", project, after={"section": section})
            return redirect(request.path)
        error = "절과 해당 없음 사유를 입력하세요."
    if action == "predicate":
        number = request.POST.get("k_number", "").strip().upper()
        saved_case = project.device.fda_510k_reviews.filter(k_number=number).first()
        values = {key: request.POST.get(key, "").strip() for key in (*FEATURES, *(f"{key}_source" for key in FEATURES))}
        if len(number) <= 20 and (number.startswith("DEMO-") if spec["example"] else
                                 saved_case is not None) and all(len(v) <= 400 for v in values.values()):
            for key in FEATURES:
                if not values[f"{key}_source"]:
                    values[key] = ""
            spec["predicate"] = {**values, "k_number": number, "record_url": saved_case.fda_detail_url if saved_case else ""}
            spec["predicate_confirmed"] = request.POST.get("confirmed") == "on"
            project.save(update_fields=["specification"])
            audit(request.user, "DENTAL_PREDICATE", project)
            return redirect(request.path)
        error = "FDA 510(k) 사례를 제품에 먼저 저장하고 확인한 값과 출처를 입력하세요."
    if action == "generate":
        if not in_scope(spec):
            error = "RA 범위 확인 필요: EBZ, 21 CFR 872.6070 및 치과 수복용 광중합 광원을 확인하세요."
        else:
            draft = project.drafts.create(author=request.user,
                                           snapshot=build_snapshot(project, references_for(project, docs), use_ai=True))
            audit(request.user, "DENTAL_DRAFT", draft)
            return redirect(request.path)

    drafts = []
    matrix = []
    if project:
        matrix = build_snapshot(project, references_for(project, docs))["rows"]
        drafts = list(project.drafts.prefetch_related("reviews__reviewer").order_by("-pk"))
        for draft in drafts:
            draft.stale = stale_sections(project, draft.snapshot, docs)
    lookup = []
    lookup_status = ""
    number = request.GET.get("k_number", "").strip().upper()
    if number and request.method == "GET":
        if re.fullmatch(r"K[0-9]{6}", number):
            try:
                lookup = case_results("k_number", number)
            except LookupError:
                lookup_status = "fda_lookup_failed"
            else:
                if not lookup:
                    lookup_status = "fda_no_matches"
    predicate = spec.get("predicate", {})
    return render(request, "pms/markets/dental.html", {
        "device": device, "project": project, "spec": spec, "form": form, "evidence_form": evidence_form, "drafts": drafts,
        "matrix": matrix, "error": error, "in_scope": bool(project and in_scope(spec)),
        "guide": project.guide if project else GUIDE,
        "estar": ESTAR, "law": LAW, "standards": STANDARDS, "fda_search": FDA_SEARCH, "lookup": lookup,
        "lookup_status": lookup_status, "number": number, "features": [
            (key, spec.get(key), predicate.get(key), predicate.get(f"{key}_source")) for key in FEATURES],
    }, status=400 if request.method == "POST" else 200)


@market_view
@never_cache
@require_http_methods(["GET", "POST"])
def draft_output(request, pk, draft_id, kind):
    device = device_for(request, pk)
    if not market_access(request.user, ("US",), device):
        raise Http404
    draft = get_object_or_404(DentalDraft.objects.select_related("project"), pk=draft_id, project__device=device)
    docs = documents_for(device)
    referenced = {ref["document_id"] for row in draft.snapshot["rows"] for ref in row["references"]}
    if not referenced.issubset(set(docs.values_list("pk", flat=True))):
        raise Http404
    if request.method == "POST" and kind == "review":
        note = request.POST.get("note", "").strip()
        if not note or len(note) > 2000 or stale_sections(draft.project, draft.snapshot, docs):
            return HttpResponse("재검토 필요 또는 검토 의견 누락", status=400)
        with transaction.atomic():
            review = draft.reviews.create(reviewer=request.user, note=note)
            audit(request.user, "DENTAL_DRAFT_REVIEW", review)
        return redirect("market-dental", pk)
    if request.method != "GET" or kind not in ("docx", "matrix", "gaps"):
        raise Http404
    payload = docx_export(draft.snapshot) if kind == "docx" else csv_export(draft.snapshot, kind)
    suffix = "docx" if kind == "docx" else "csv"
    return FileResponse(io.BytesIO(payload), as_attachment=True, filename=f"dental-{draft.pk}-{kind}.{suffix}")


@market_view
@never_cache
@require_http_methods(["GET"])
def evidence_download(request, pk, document_id):
    device = device_for(request, pk)
    if not market_access(request.user, ("US",), device):
        raise Http404
    document = get_object_or_404(documents_for(device).distinct(), pk=document_id, dentalevidence__project__device=device)
    attachment = document.primary_file
    return FileResponse(io.BytesIO(safe_attachment_bytes(attachment)), as_attachment=True,
                        filename=attachment.original_name or document.number)
