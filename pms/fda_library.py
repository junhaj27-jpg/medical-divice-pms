"""Versioned public sources; never derive a product classification from library links."""
import hashlib
import json
import re
from urllib.parse import urlsplit

from django import forms
from django.db import transaction
from django.db.models import Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .fda_library_models import FDAReferenceVersion, ProjectFDAReference
from .market_models import MarketEvidence
from .market_service import market_access, product_markets
from .market_views import market_view
from .services import audit

DEVICE_TYPES = ("mri-equipment", "mri-software", "mr-environment")


def official_url(value):
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.netloc not in ("www.fda.gov", "www.accessdata.fda.gov", "www.ecfr.gov") or parts.fragment:
        raise forms.ValidationError("FDA/eCFR HTTPS 공식 URL을 입력하세요.")
    return value


def record_reference(values, actor=None):
    values = dict(values)
    identity = {k: str(v) if k in ("issued_on", "revised_on") else v for k, v in values.items()
                if k not in ("checked_on", "key", "version", "parent", "recorded_by", "content_hash")}
    fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    key = values.pop("key")
    with transaction.atomic():
        list(FDAReferenceVersion.objects.select_for_update().filter(key=key).values_list("pk", flat=True))
        existing = FDAReferenceVersion.objects.filter(key=key, content_hash=fingerprint).first()
        if existing:
            return existing, False
        latest = FDAReferenceVersion.objects.filter(key=key).order_by("-version").first()
        values.pop("parent", None)
        source = FDAReferenceVersion.objects.create(key=key, version=1 if not latest else latest.version + 1,
            parent=latest, content_hash=fingerprint, recorded_by=actor, **values)
        if actor:
            audit(actor, "FDA_SOURCE_VERSION", source, after={"key": key, "version": source.version})
        return source, True


class SourceForm(forms.Form):
    key = forms.SlugField(max_length=60, label="출처 계열 ID")
    title = forms.CharField(max_length=500, label="문서명")
    source_type = forms.ChoiceField(choices=FDAReferenceVersion._meta.get_field("source_type").choices, label="출처 유형")
    document_version = forms.CharField(max_length=160, label="문서 판본 / 발행 정보")
    issued_on = forms.DateField(required=False, label="최초 발행일 (미확인 시 비움)")
    revised_on = forms.DateField(required=False, label="개정일 (미확인 시 비움)")
    checked_on = forms.DateField(label="확인일")
    official_url = forms.URLField(max_length=1000, validators=[official_url], label="공식 원문 URL")
    pdf_url = forms.URLField(max_length=1000, required=False, validators=[official_url], label="PDF URL")
    scope = forms.CharField(max_length=4000, widget=forms.Textarea, label="적용 범위 / 제한사항")
    device_types = forms.MultipleChoiceField(choices=[(v, v) for v in DEVICE_TYPES], label="자료 수집 유형")
    section = forms.CharField(max_length=240, label="절·조항")
    page = forms.IntegerField(min_value=0, max_value=10000, initial=0, label="PDF 페이지 (HTML은 0)")
    standard_number = forms.CharField(max_length=100, required=False, label="표준 번호")
    edition = forms.CharField(max_length=160, required=False, label="FDA 인정 판본")
    recognition_number = forms.CharField(max_length=80, required=False, label="FDA 인정 번호")
    recognition_scope = forms.CharField(max_length=2000, required=False, label="FDA 인정 범위 / 미확인 시 RA 확인 필요")

    def values(self):
        data = dict(self.cleaned_data)
        section, page = data.pop("section"), data.pop("page")
        metadata = {key: data.pop(key) or "RA 확인 필요" for key in
                    ("standard_number", "edition", "recognition_number", "recognition_scope")}
        return {**data, "sections": [{"clause": section, "page": page}], "pages": {}, "metadata": metadata,
                "retrieval_status": "manual_metadata", "failure_reason": "본문 자동 수집 미실행 · 공식 원문 확인 필요"}


def source_snapshot(project):
    rows = []
    for link in project.fda_references.select_related("source", "product_evidence").order_by("pk"):
        s = link.source
        rows.append({"id": link.pk, "section": link.section, "source_id": s.pk, "key": s.key, "version": s.version,
            "document_version": s.document_version, "title": s.title, "source_type": s.source_type,
            "url": s.official_url, "pdf_url": s.pdf_url, "clause": link.clause, "page": link.page,
            "checked_on": str(s.checked_on), "issued_on": str(s.issued_on or ""), "revised_on": str(s.revised_on or ""),
            "content_hash": s.content_hash, "rationale": link.rationale, "scope": s.scope,
            "metadata": s.metadata, "retrieval_status": s.retrieval_status,
            "failure_reason": s.failure_reason, "superseded": s.revisions.exists()})
    selected = {(row["section"], row["key"]): row["source_id"] for row in rows}
    return [row for row in rows if selected[row["section"], row["key"]] == row["source_id"]]


def link_reference(project, user, data):
    from .dental_workflow import template_items
    section = data.get("section", "")
    if section not in {item["id"] for item in template_items(project)}:
        raise Http404
    if not re.fullmatch(r"[0-9]{1,18}", data.get("source_id", "")):
        raise Http404
    source = get_object_or_404(FDAReferenceVersion, pk=data.get("source_id"))
    clause, rationale = data.get("clause", "").strip(), data.get("rationale", "").strip()
    page_value = data.get("page", "0")
    if data.get("citation"):
        clause, _, page_value = data["citation"].rpartition("|")
    try:
        page = int(page_value)
    except ValueError:
        return "절·페이지를 확인하세요."
    if (not clause or len(clause) > 240 or not rationale or len(rationale) > 2000 or page < 0 or page > 10000
            or not any(x["clause"] == clause and x["page"] == page for x in source.sections)):
        return "등록된 출처의 절·페이지를 선택하고 적용 검토 사유를 입력하세요."
    with transaction.atomic():
        evidence, created = MarketEvidence.objects.get_or_create(device=project.device, scope="US",
            reference_key="fda-library-" + str(source.pk), version=1, defaults={
                "title": source.title[:240], "official_url": source.official_url, "clause": clause, "language": "en",
                "excerpt": source.scope, "checked_on": source.checked_on, "created_by": user,
                "is_example": bool(project.specification.get("example")),
                "document_type": "FDA_GUIDANCE" if source.source_type == "guidance" else "REFERENCE",
                "document_metadata": {"library_source_id": source.pk, "source_type": source.source_type,
                                      "document_version": source.document_version, "content_hash": source.content_hash}})
        link, created = ProjectFDAReference.objects.get_or_create(project=project, source=source, section=section, clause=clause,
            page=page, defaults={"actor": user, "rationale": rationale, "product_evidence": evidence})
        if created:
            audit(user, "FDA_PROJECT_SOURCE", link, after={"source_id": source.pk, "section": section})
    return ""


@market_view
@never_cache
@require_http_methods(["GET", "POST"])
def library(request, pk=None):
    if not market_access(request.user, ("US",)):
        raise Http404
    source = get_object_or_404(FDAReferenceVersion, pk=pk) if pk else None
    initial = {"checked_on": timezone.localdate()}
    if source:
        initial.update({f: getattr(source, f) for f in ("key", "title", "source_type", "document_version", "issued_on", "revised_on",
            "official_url", "pdf_url", "scope", "device_types")})
        initial.update(source.metadata)
        initial.update(source.sections[0] if source.sections else {})
        initial["section"] = initial.get("clause", "")
    form = SourceForm(request.POST if request.method == "POST" else None, initial=initial)
    if request.method == "POST" and form.is_valid():
        if source and form.cleaned_data["key"] != source.key:
            form.add_error("key", "개정본은 같은 출처 계열에 등록하세요.")
        else:
            record, _ = record_reference(form.values(), request.user)
            return redirect("market-fda-source", record.pk)
    term = request.GET.get("q", "").strip()[:200]
    kind = request.GET.get("device_type", "")
    # Latest per family; historical versions remain directly addressable.
    latest = FDAReferenceVersion.objects.values("key").annotate(pk_latest=Max("pk")).values("pk_latest")
    sources = FDAReferenceVersion.objects.filter(pk__in=latest)
    if term and term.upper() not in ("MRI/MR", "MRI", "MR"):
        sources = sources.filter(Q(title__icontains=term) | Q(scope__icontains=term) | Q(pages__icontains=term) | Q(metadata__icontains=term))
    if kind in DEVICE_TYPES:
        sources = sources.filter(device_types__icontains=kind)
    projects = []
    if source:
        from .dental_models import DentalProject
        projects = DentalProject.objects.filter(market="US", device_id__in=product_markets(request.user).filter(market="US").values("device_id")).select_related("device")
        # Global RA accounts may also use existing products without a registration row.
        from .market_service import scoped
        if not scoped(request.user):
            projects = DentalProject.objects.filter(market="US").select_related("device")
    return render(request, "pms/markets/fda_library.html", {"source": source, "sources": sources[:100], "form": form,
        "q": term, "selected_type": kind, "device_types": DEVICE_TYPES, "projects": projects,
        "versions": FDAReferenceVersion.objects.filter(key=source.key) if source else [],
        "related_regulation": FDAReferenceVersion.objects.filter(key=source.metadata.get("related_regulation_key"),
            version=source.metadata.get("related_regulation_version", 1)).first() if source else None,
        "body_pages": source.pages.items() if source else [],
    }, status=400 if request.method == "POST" else 200)
