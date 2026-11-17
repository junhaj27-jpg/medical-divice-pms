"""Registered model/configuration -> existing versioned writing workflow."""
import io
from copy import deepcopy
from zipfile import ZipFile

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.cache import never_cache

from .mri_models import MRIConfiguration, MRIApplicabilityReview
from .market_views import device_for, market_view
from .market_service import market_access
from .market_models import ProductMarket
from .dental_models import DentalProject, WritingTemplate
from .services import audit

DOCUMENTS = {
    "description": ("Device Description and Model Configuration", {"MRI.USE", "MRI.SPEC", "MRI.COIL"}),
    "predicate": ("Predicate Device Comparison", {"MRI.PRED"}),
    "performance": ("Performance Testing Summary", {"MRI.IMG", "MRI.SAFE", "MRI.EMC", "MRI.SW", "MRI.CLIN", "MRI.RISK", "MRI.STD"}),
    "labeling": ("Labeling and IFU Review", {"MRI.LABEL"}),
}


def configuration_payload(device):
    c = device.mri_configurations.first()
    if not c:
        return None
    return {"id":c.pk,"version":c.version,"family_id":c.family_id,"device_id":device.pk,
        "product_name":device.name,"manufacturer":device.manufacturer.name,"model":device.model_number,
        **{field:getattr(c,field) for field in ("configuration_name","intended_use","target_population","users","environment",
              "magnet_type","rf_coil","modes","accessories","software_version","is_example")},
        "field_strength_t": str(c.field_strength_t) if c.field_strength_t is not None else ""}


def registered_specification(device):
    c = configuration_payload(device)
    if not c: raise Http404
    return {"registered_configuration":c,"product_name":c["product_name"],"model":c["model"],
        "manufacturer":c["manufacturer"],"intended_use":c["intended_use"],"target_population":c["target_population"],
        "users":c["users"],"environment":c["environment"],"configuration":c["configuration_name"],
        "field_strength":c["field_strength_t"] + " T" if c["field_strength_t"] else "",
        "magnet_type":c["magnet_type"],"coils":c["rf_coil"],"modes":c["modes"],"accessories":c["accessories"],
        "software":c["software_version"],"product_version":c["software_version"] or "Not recorded",
        "example":c["is_example"],"product_code":"","regulation":"","confirmed_pathway":"","scope_confirmed":False}


def registration_changed(project):
    saved = project.specification.get("registered_configuration")
    return bool(saved and saved != configuration_payload(project.device))


def ensure_profile(device, user):
    from .models import RegulatoryProfile, BusinessPartner
    from .ra_services import save_record
    profile = RegulatoryProfile.objects.filter(device=device,jurisdiction="US").first()
    if profile: return profile
    organization,_ = BusinessPartner.objects.get_or_create(name=device.manufacturer.name)
    return save_record(RegulatoryProfile(),user,dict(device=device,jurisdiction="US",organization=organization,
        organization_role="MANUFACTURER",title=f"US MRI {device.model_number}",owner=user,
        is_example=bool(device.mri_configurations.first().is_example)),"MRI document collection project")


@market_view
@require_POST
@transaction.atomic
def start(request, pk):
    from .dental_views import guide_for
    from .fda_library import FDAReferenceVersion, link_reference
    device = device_for(request,pk,lock=True)
    if device.product_type != "MRI" or not market_access(request.user,("US",),device): raise Http404
    project = DentalProject.objects.filter(device=device,market="US").first()
    if not project:
        template = WritingTemplate.objects.filter(key="mri-equipment",state="PUBLISHED").order_by("-version").first()
        if not template:raise Http404
        project = DentalProject.objects.create(device=device,market="US",owner=request.user,template=template,
            guide=guide_for(),specification=registered_specification(device))
        ensure_profile(device,request.user)
        for item in template.items:
            source = FDAReferenceVersion.objects.filter(key=item.get("source_key", "mrdd")).order_by("-version").first()
            if source:
                link_reference(project,request.user,{"section":item["id"],"source_id":str(source.pk),
                    "clause":item["source_section"],"page":str(item["page"]),
                    "rationale":"Initial review reference only; subject-device applicability and pathway require RA confirmation"})
        classification = FDAReferenceVersion.objects.filter(key="mri-lnh").order_by("-version").first()
        if classification:
            item = classification.sections[0]
            link_reference(project,request.user,{"section":"MRI.USE","source_id":str(classification.pk),
                "clause":item["clause"],"page":str(item["page"]),"rationale":"LNH classification candidate; not a product classification decision"})
        audit(request.user,"MRI_WRITING_PROJECT",project,after={"configuration_id":project.specification["registered_configuration"]["id"]})
    elif project.template and project.template.key=="mri-equipment" and not project.specification.get("registered_configuration"):
        sync_product(project,request.user)
        ensure_profile(device,request.user)
    return redirect("market-writing",device.pk)


def sync_product(project, user):
    old = project.specification
    fresh = registered_specification(project.device)
    project.specification = {**old,**fresh}
    if not old.get("registered_configuration"):
        project.specification["previous_project_inputs"]=old
    project.save(update_fields=["specification"])
    audit(user,"MRI_PRODUCT_SYNC",project,after={"configuration_id":fresh["registered_configuration"]["id"]})


def review_evidence(project, user, data):
    if not str(data.get("evidence_id", "")).isdigit(): raise Http404
    evidence = get_object_or_404(project.evidence.select_related("document__primary_file"),pk=data["evidence_id"])
    config = project.specification.get("registered_configuration",{}).get("id")
    if not config or registration_changed(project):
        return "최신 제품 구성을 먼저 동기화하세요."
    reason = data.get("rationale", "").strip()
    if data.get("decision") not in ("accept","reject") or not reason or len(reason)>2000:
        return "적용 여부와 판단 사유를 입력하세요."
    previous = evidence.mri_reviews.filter(configuration_id=config).first()
    if data.get("previous", "0") != str(previous.pk if previous else 0):
        return "검토 이력이 변경됐습니다. 최신 화면을 다시 열어 저장하세요."
    doc=evidence.document
    review=MRIApplicabilityReview.objects.create(evidence=evidence,configuration_id=config,decision=data["decision"],
        rationale=reason,source_identity=[doc.revision,doc.primary_file_id,doc.primary_file.sha256],reviewer=user)
    audit(user,"MRI_EVIDENCE_APPLICABILITY",review,after={"evidence_id":evidence.pk,"configuration_id":config,"decision":review.decision})
    return ""


class DocumentUploadForm(forms.Form):
    number = forms.CharField(label="문서번호",max_length=80)
    version = forms.IntegerField(label="문서 버전",min_value=1)
    title = forms.CharField(label="문서명",max_length=200)
    document_kind = forms.ChoiceField(label="증빙 유형",choices=[(v,v) for v in ("Specification","Component list","Design","Test report","Risk management","Label / IFU")])
    file = forms.FileField(label="PDF 또는 UTF-8 TXT/CSV (기존 파일 검사 적용)")


@market_view
@never_cache
@require_http_methods(["GET","POST"])
def upload_document(request,pk):
    from .models import Attachment, ControlledDocument
    from .file_security import normalized_name, scan_attachment
    from .ra_services import save_record
    device=device_for(request,pk)
    if device.product_type!="MRI" or not market_access(request.user,("US",),device):raise Http404
    form=DocumentUploadForm(request.POST if request.method=="POST" else None,request.FILES or None)
    if form.is_valid():
        profile=ensure_profile(device,request.user)
        if ControlledDocument.objects.filter(profile=profile,number=form.cleaned_data["number"],version=form.cleaned_data["version"]).exists():
            form.add_error("version","이 문서번호와 버전이 이미 있습니다. 기존 문서를 연결하거나 새 버전을 등록하세요.")
        else:
            try:
                file=Attachment(ra_profile=profile,file=form.cleaned_data["file"],original_name=normalized_name(form.cleaned_data["file"].name),uploaded_by=request.user)
                file.full_clean();file.save();scan_attachment(file,request.user)
                previous=ControlledDocument.objects.filter(profile=profile,number=form.cleaned_data["number"]).order_by("-version").first()
                if previous and form.cleaned_data["version"]<=previous.version:raise ValidationError("새 버전 번호는 이전 버전보다 커야 합니다.")
                save_record(ControlledDocument(),request.user,dict(profile=profile,owner=request.user,title=form.cleaned_data["title"],
                    number=form.cleaned_data["number"],version=form.cleaned_data["version"],category="TECHNICAL",primary_file=file,
                    supersedes=previous,change_reason=form.cleaned_data["document_kind"],is_example=bool(device.mri_configurations.first().is_example)),"MRI evidence upload")
                return redirect("market-writing",pk)
            except ValidationError as exc:form.add_error(None,exc)
    return render(request,"pms/form.html",{"form":form,"title":"MRI 제품 증빙 등록 · 검사 통과 후 체크리스트에 연결"},status=400 if request.method=="POST" else 200)


def document_snapshot(snapshot,kind):
    result=deepcopy(snapshot)
    if kind in DOCUMENTS:
        result["rows"]=[row for row in result["rows"] if row["section"] in DOCUMENTS[kind][1]]
        result["document_kind"]=kind
    return result


def bundle_export(snapshot):
    from .dental_workflow import docx_export,csv_export
    out=io.BytesIO()
    with ZipFile(out,"w") as archive:
        for key in DOCUMENTS:
            part=document_snapshot(snapshot,key)
            if part["rows"]:archive.writestr(key+".docx",docx_export(part))
        for kind in ("matrix","gaps","mapping"):
            archive.writestr(kind+".csv",csv_export(snapshot,kind))
    return out.getvalue()


def mri_tables(snapshot):
    """Word tables use only frozen, selected evidence; excluded results stay withheld."""
    import re
    from xml.sax.saxutils import escape
    def cell(value):
        text=escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]","",str(value)))
        return '<w:tc><w:p><w:r><w:t xml:space="preserve">'+text+'</w:t></w:r></w:p></w:tc>'
    def table(headers,rows):
        return '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>'+''.join('<w:tr>'+''.join(cell(v) for v in row)+'</w:tr>' for row in [headers,*rows])+'</w:tbl>'
    spec=snapshot["specification"]; rows=snapshot["rows"];sections={row["section"] for row in rows};out=[]
    refs=[ref for row in rows for ref in row["references"] if ref["id"] in row["selected"]]
    def backed(key,scope=None):
        value=str(spec.get(key) or "")
        found=next((ref for ref in (scope if scope is not None else refs) if value and " ".join(value.split()) in " ".join(ref["excerpt"].split())),None)
        return (value,found["citation"]) if found else ("Evidence needed", "No selected product evidence")
    if sections & {"MRI.USE","MRI.SPEC","MRI.COIL"}:
        out.append(table(["Model / configuration field","Evidence-supported value","Product evidence version / location"],
            [(key,*backed(key)) for key in ("model","intended_use","target_population","users","environment","field_strength","magnet_type","coils","modes","accessories","software","configuration")]))
    if "MRI.PRED" in sections:
        row=next(r for r in rows if r["section"]=="MRI.PRED")
        selected=[ref for ref in row["references"] if ref["id"] in row["selected"]]
        predicate=spec.get("predicate",{});comparison=[]
        for key in ("intended_use","field_strength","coils","modes","software"):
            subject,citation=backed(key,selected);value=predicate.get(key);source=predicate.get(key+"_source")
            comparison.append((key,subject,citation,value if value and source else "Unavailable in public materials",source or "RA confirmation required","RA review required; no SE determination"))
        out.append(table(["Characteristic","Subject","Product evidence","Predicate candidate","Public source (RA recorded)","Review"],comparison))
    reports=[]
    for row in rows:
        if row["section"] not in DOCUMENTS["performance"][1]:continue
        for ref in row["references"]:
            if ref.get("evidence_role")!="test":continue
            applied=ref["id"] in row["selected"]
            reports.append((row["section"],ref["model"],ref.get("coil",""),ref.get("software_version",""),
                ref.get("conditions", ""),ref.get("method",""),ref.get("acceptance",""),
                ref.get("result","") if applied else "WITHHELD — not applied to target model",ref["citation"],
                (ref.get("applicability_review") or {}).get("rationale") or ("Selected source evidence; RA review" if applied else "RA applicability review required")))
    if sections & DOCUMENTS["performance"][1]:
        out.append(table(["Item","Source model","Source coil","Source software","Conditions","Method","Acceptance","Result","Report version/page","Applicability"],reports or [("Evidence needed",)*10]))
    if "MRI.LABEL" in sections:
        row=next(r for r in rows if r["section"]=="MRI.LABEL")
        status={"근거 연결":"Evidence linked","증빙 연결":"Evidence linked","자료 부족":"Evidence needed","자료 필요":"Evidence needed","RA 검토 필요":"RA review required","해당 없음":"Not applicable","재검토 필요":"Re-review required"}.get(row["status"],"RA review required")
        out.append(table(["Label / IFU version and page","Evidence-supported text","Review status","Supplement request"],
            [(ref["citation"],ref["excerpt"] if ref["id"] in row["selected"] else "Evidence needed",status,"See Korean supplement list" if row["gaps"] else "RA review") for ref in row["references"]] or [("Evidence needed",)*4]))
    return ''.join(out)
