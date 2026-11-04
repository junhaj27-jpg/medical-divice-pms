from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db import models

from . import foreign as service
from .approval_integrity import digest
from .foreign_models import ForeignApplication, ForeignDocument, ForeignResult, ForeignSubmission, ForeignSupplement
from .models import Attachment, MedicalDevice, RegulatoryProfile, SoftwareRelease
from .ra_services import require_admin, require_ra
from .services import role

EDIT = (service.STAGE.PREPARATION, service.STAGE.REVIEW)


class Filters(forms.Form):
    device = forms.ModelChoiceField(label="제품", queryset=MedicalDevice.objects.all(), required=False)
    market = forms.ChoiceField(label="시장", choices=[("", "전체")] + ForeignApplication.Market.choices, required=False)
    stage = forms.ChoiceField(label="상태", choices=[("", "전체")] + service.STAGE.choices, required=False)
    owner = forms.ModelChoiceField(label="담당자", queryset=get_user_model().objects.filter(is_active=True), required=False)


def build_form(model, fields, data=None, instance=None, case=None, initial=None, device=None):
    widgets = {name: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
               for name in fields if isinstance(model._meta.get_field(name), models.DateField)}
    form = forms.modelform_factory(model, fields=fields, widgets=widgets)(data, instance=instance, initial=initial)
    if "owner" in form.fields:
        from django.db.models import Q
        form.fields["owner"].queryset = get_user_model().objects.filter(
            Q(profile__role__in=["RA_QA", "ADMIN"]) | Q(is_superuser=True), is_active=True,
        )
    if "profile" in form.fields:
        profiles = RegulatoryProfile.objects.filter(jurisdiction__in=ForeignApplication.Market.values)
        form.fields["profile"].label = "제품 규제 프로필 (US/EU)"
        form.fields["profile"].queryset = profiles.filter(device=device) if device else profiles
        if case:
            for name in ("profile", "market", "is_example"):
                form.fields[name].disabled = True
        if device:
            form.fields["release"].queryset = SoftwareRelease.objects.filter(device=device)
            form.fields["previous"].queryset = ForeignApplication.objects.filter(profile__device=device)
    if case:
        for field in ("evidence", "response"):
            if field in form.fields:
                form.fields[field].queryset = Attachment.objects.filter(ra_profile=case.profile, scan_status="PASSED")
    return form


class SupplementForm(forms.Form):
    requested_on = forms.DateField(label="요청일", widget=forms.DateInput(attrs={"type": "date"}))
    due_on = forms.DateField(label="회신 기한", widget=forms.DateInput(attrs={"type": "date"}))
    owner = forms.ModelChoiceField(label="담당자", queryset=get_user_model().objects.filter(is_active=True))
    basis = forms.CharField(label="요청 내용 및 기한 근거", widget=forms.Textarea)


class RejectForm(forms.Form):
    reason = forms.CharField(label="반려 사유", widget=forms.Textarea)


@login_required
def listing(request, device_pk=None):
    require_ra(request.user)
    device = get_object_or_404(MedicalDevice, pk=device_pk) if device_pk else None
    query = ForeignApplication.objects.select_related("profile__device", "owner").order_by("-pk")
    form = Filters(request.GET)
    if device:
        query = query.filter(profile__device=device)
        del form.fields["device"]
    if form.is_valid():
        for name, value in form.cleaned_data.items():
            if value:
                query = query.filter(**{("profile__device" if name == "device" else name): value})
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "pms/foreign/list.html", {
        "form": form, "device": device, "page": Paginator(query, 30).get_page(request.GET.get("page")),
        "params": params.urlencode(),
    })


@login_required
def edit(request, pk=None, device_pk=None):
    require_ra(request.user)
    case = get_object_or_404(ForeignApplication, pk=pk) if pk else None
    device = case.profile.device if case else get_object_or_404(MedicalDevice, pk=device_pk) if device_pk else None
    form = build_form(ForeignApplication, service.APP_FIELDS, request.POST if request.method == "POST" else None,
                      instance=case, case=case, initial={"owner": request.user}, device=device)
    if request.method == "POST" and form.is_valid():
        try:
            saved = service.save_application(request.user, form.cleaned_data, pk)
            return redirect("foreign-detail", saved.pk)
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
    return render(request, "pms/foreign/form.html", {"form": form, "case": case, "title": "해외 인허가 신청 범위"})


@login_required
def document_edit(request, pk, document_pk=None):
    require_ra(request.user)
    case = get_object_or_404(ForeignApplication, pk=pk)
    document = get_object_or_404(case.documents, pk=document_pk) if document_pk else None
    form = build_form(ForeignDocument, service.DOC_FIELDS, request.POST if request.method == "POST" else None,
                      instance=document, case=case, initial={"owner": request.user})
    if request.method == "POST" and form.is_valid():
        try:
            service.save_document(request.user, pk, form.cleaned_data, document_pk)
            return redirect("foreign-detail", pk)
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
    return render(request, "pms/foreign/form.html", {"form": form, "case": case, "title": "내부 준비 체크리스트 편집"})


@login_required
def detail(request, pk):
    require_ra(request.user)
    case = get_object_or_404(ForeignApplication.objects.select_related("profile__device", "release", "previous", "owner"), pk=pk)
    history = service.approvals(case)
    latest = history.first()
    stale = bool(latest and (latest.superseded or latest.snapshot.get("hash") != digest(service.manifest(case))))
    supplements = list(case.supplements.select_related("task__assignee", "response").order_by("pk"))
    today = timezone.localdate()
    from django.conf import settings
    for item in supplements:
        days = (item.due_on - today).days
        item.deadline = "회신 완료" if item.responded_on else "기한 초과" if days < 0 else "기한 임박" if days <= settings.TASK_DUE_SOON_DAYS else "회신 대기"
    return render(request, "pms/foreign/detail.html", {
        "case": case, "editable": case.stage in EDIT, "latest": latest, "stale": stale, "history": history,
        "can_reject": role(request.user) == "ADMIN" and case.stage == "REVIEW" and latest and latest.decision == "PENDING" and not stale,
        "separate_approver": request.user.pk != case.created_by_id,
        "can_submit": case.stage == "REVIEW" and latest and latest.decision == "APPROVED" and not stale,
        "documents": case.documents.select_related("owner", "evidence").order_by("pk"),
        "supplements": supplements, "submissions": case.submissions.select_related("evidence").all(),
        "files": Attachment.objects.filter(ra_profile=case.profile).order_by("-pk")[:30],
    })


ACTIONS = {
    "review": ("내부 검토 요청", None, ()),
    "approve": ("관리자 내부 승인", None, ()),
    "reject": ("관리자 내부 반려", RejectForm, ()),
    "submit": ("제출 이력 기록", ForeignSubmission, ("submitted_on", "reference", "evidence")),
    "supplement": ("보완 요청 등록", SupplementForm, ()),
    "respond": ("보완 회신 기록", ForeignSupplement, ("response", "responded_on")),
    "result": ("외부 심사 결과 기록", ForeignResult, ("kind", "issuer", "issued_on", "reference", "expires_on", "evidence")),
}


@login_required
def action(request, pk, operation, supplement_pk=None):
    from django.http import Http404
    require_ra(request.user)
    if operation not in ACTIONS or (operation == "respond") != (supplement_pk is not None):
        raise Http404
    if operation in ("approve", "reject"):
        require_admin(request.user)
    case = get_object_or_404(ForeignApplication, pk=pk)
    if supplement_pk is not None:
        get_object_or_404(case.supplements, pk=supplement_pk)
    title, model, fields = ACTIONS[operation]
    data = request.POST if request.method == "POST" else None
    form = build_form(model, fields, data, case=case) if fields else (model or forms.Form)(data)
    if request.method == "POST" and form.is_valid():
        try:
            values = dict(form.cleaned_data)
            if supplement_pk is not None:
                values["supplement_id"] = supplement_pk
                if not values["responded_on"]:
                    raise ValidationError("회신일이 필요합니다.")
            service.operate(request.user, pk, operation, values)
            messages.success(request, title + " 완료")
            return redirect("foreign-detail", pk)
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
    return render(request, "pms/foreign/form.html", {"form": form, "case": case, "title": title})

