from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone, translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from . import market_service as svc
from .market_forms import CaseMarketForm, EvidenceForm, LanguageForm, RegistrationForm, TranslationForm
from .market_i18n import CODES
from .market_models import COUNTRIES, EU_COUNTRIES, CaseMarket, MarketEvidence, MarketTranslation, ProductMarket
from .foreign_models import ForeignApplication
from .models import MedicalDevice, Profile
from .services import audit, visible_complaints


def market_view(view):
    from functools import wraps

    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        svc.require_workspace(request.user)
        return view(request, *args, **kwargs)
    return wrapped


def country(request, code, *, unknown=False):
    if code not in svc.allowed_markets(request.user) or (code == "XX" and not unknown):
        raise Http404
    return code


def device_for(request, pk, lock=False):
    qs = MedicalDevice.objects.all()
    if svc.scoped(request.user):
        qs = qs.filter(pk__in=svc.product_markets(request.user).values("device_id"))
    return get_object_or_404(qs.select_for_update() if lock else qs, pk=pk)


def complaint_for(request, pk, lock=False):
    qs = visible_complaints(request.user)
    if svc.scoped(request.user):
        qs = qs.filter(pk__in=svc.case_markets(request.user).values("complaint_id"))
    return get_object_or_404(qs.select_for_update(of=("self",)) if lock else qs, pk=pk)


def registration_evidence(registration):
    return svc.evidence_versions(MarketEvidence.objects.filter(
        device_id=registration.device_id, scope__in=svc.source_scopes(registration.market),
        is_example=registration.is_example,
    ).select_related("reviewer"))


def matching_registration(entry):
    return ProductMarket.objects.filter(device_id=entry.complaint.device_id, market=entry.market,
                                        is_example=entry.complaint.is_example).first()


@login_required
@require_POST
@transaction.atomic
def language(request):
    form = LanguageForm(request.POST, lang=request.ui_language)
    if not form.is_valid():
        return form_page(request, form, "language", status=400)
    profile, _ = Profile.objects.select_for_update().get_or_create(user=request.user)
    before = profile.ui_language
    profile.ui_language = form.cleaned_data["language"]
    if before != profile.ui_language:
        profile.save(update_fields=["ui_language"])
        audit(request.user, "UI_LANGUAGE", profile, before={"language": before},
              after={"language": profile.ui_language})
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect("dashboard")


@market_view
@require_safe
def dashboard(request):
    markets = svc.allowed_markets(request.user)
    selected = request.GET.get("market")
    if selected:
        markets = (country(request, selected, unknown=True),)
    registrations = svc.product_markets(request.user).filter(market__in=markets)
    cases = svc.case_markets(request.user).filter(market__in=markets)
    today = timezone.localdate()
    reconciled = ProductMarket.objects.filter(
        device_id=OuterRef("complaint__device_id"), market=OuterRef("market"),
        is_example=OuterRef("complaint__is_example"), eu_assessment__in=("ALIGNED", "NA"),
    ).exclude(eu_rationale="")
    pending = cases.filter(Q(reviewed=False) | (Q(market__in=EU_COUNTRIES) & ~Exists(reconciled)))
    return render(request, "pms/markets/dashboard.html", {
        "markets": svc.allowed_markets(request.user), "selected": selected,
        "summary": registrations.values("market", "status").annotate(total=Count("pk")).order_by("market", "status"),
        "registrations": Paginator(registrations.order_by("market", "device__name"), 30).get_page(request.GET.get("page")),
        "expiring": registrations.filter(status="REGISTERED", expires_on__range=(today, today + timedelta(days=90)))
        .order_by("expires_on")[:30],
        "pending": pending.exclude(complaint__status="CLOSED").order_by("market", "-pk")[:30],
    })


@market_view
@require_safe
def product(request, pk):
    device = device_for(request, pk)
    rows = svc.product_markets(request.user).filter(device=device).order_by("market")
    return render(request, "pms/markets/product.html", {
        "device": device, "rows": rows,
        "available": [code for code in svc.allowed_markets(request.user) if code in COUNTRIES]
        if not svc.scoped(request.user) else (),
        "has_legacy": not svc.scoped(request.user) and ForeignApplication.objects.filter(profile__device=device).exists(),
    })


def form_page(request, form, title, status=200, **context):
    return render(request, "pms/markets/form.html", {"form": form, "title_key": title, **context}, status=status)


@market_view
@require_http_methods(["GET", "HEAD", "POST"])
@transaction.atomic
def registration(request, pk, code):
    country(request, code, unknown=True)
    device = device_for(request, pk, lock=request.method == "POST")
    row = svc.product_markets(request.user).filter(device=device, market=code).first()
    if not row and (svc.scoped(request.user) or code == "XX"):
        raise Http404
    row = row or ProductMarket(device=device, market=code)
    before = svc_product_state(row)
    form = RegistrationForm(request.POST if request.method == "POST" else None, instance=row,
                            lang=request.ui_language, actor=request.user, eu=code in EU_COUNTRIES)
    evidence = registration_evidence(row)
    if request.method == "POST" and form.is_valid():
        row = form.save(commit=False)
        row.eu_versions = sorted(source.pk for source, _ in evidence) if code in EU_COUNTRIES else []
        row.save()
        audit(request.user, "MARKET_REGISTRATION", row, before=before, after=svc_product_state(row))
        return redirect("market-registration", pk, code)
    return form_page(request, form, "registration", market=code, device=device, evidence=evidence,
                     source_scopes=(code, "EU") if code in EU_COUNTRIES and not svc.scoped(request.user)
                     else (code,) if code in COUNTRIES else (),
                     registration=row)


def svc_product_state(row):
    return {name: str(getattr(row, name) or "") for name in RegistrationForm.optional_fields} | {
        "market": row.market, "status": row.status, "eu_assessment": row.eu_assessment,
        "eu_rationale": row.eu_rationale, "eu_versions": row.eu_versions, "na_fields": row.na_fields,
    }


@market_view
@require_http_methods(["GET", "HEAD", "POST"])
@transaction.atomic
def evidence_new(request, pk, code, scope):
    country(request, code)
    if scope not in svc.source_scopes(code) or (scope == "EU" and svc.scoped(request.user)):
        raise Http404
    device = device_for(request, pk, lock=request.method == "POST")
    registration = get_object_or_404(svc.product_markets(request.user), device=device, market=code)
    row = MarketEvidence(device=device, scope=scope, created_by=request.user, is_example=registration.is_example)
    form = EvidenceForm(request.POST if request.method == "POST" else None, instance=row, lang=request.ui_language, actor=request.user)
    if request.method == "POST" and form.is_valid():
        row = form.save(commit=False)
        current = MarketEvidence.objects.filter(device=device, scope=scope, reference_key=row.reference_key)
        if current.exclude(is_example=row.is_example).exists():
            form.add_error("reference_key", form.fields["reference_key"].error_messages["invalid"])
        else:
            row.version = (current.aggregate(latest=Max("version"))["latest"] or 0) + 1
            row.reviewer = request.user if form.cleaned_data["verified"] else None
            row.save()
            if scope == "EU" or scope in EU_COUNTRIES:
                affected = ProductMarket.objects.filter(
                    device=device, market__in=EU_COUNTRIES if scope == "EU" else (scope,),
                    is_example=row.is_example, eu_assessment__in=("ALIGNED", "NA"),
                )
                for registration in affected:
                    prior = registration.eu_assessment
                    registration.eu_assessment = "UNKNOWN"
                    registration.save(update_fields=["eu_assessment"])
                    audit(request.user, "MARKET_EU_REVIEW_RESET", registration,
                          before={"eu_assessment": prior}, after={"source_id": row.pk})
            audit(request.user, "MARKET_EVIDENCE_VERSION", row, after={"scope": scope, "version": row.version})
            return redirect("market-evidence", pk, code, row.pk)
    return form_page(request, form, "new_evidence", market=scope, device=device)


def registration_source(request, pk, code, source_pk):
    country(request, code)
    registration = get_object_or_404(svc.product_markets(request.user), device_id=pk, market=code)
    return get_object_or_404(MarketEvidence, pk=source_pk, device_id=pk, scope__in=svc.source_scopes(code),
                             is_example=registration.is_example)


def source_page(request, source, **context):
    newer = MarketEvidence.objects.filter(device=source.device, scope=source.scope,
                                          reference_key=source.reference_key, version__gt=source.version).exists()
    translations = source.translations.select_related("reviewer").order_by("language", "-version")
    candidates = [item for item in translations if item.language == request.GET.get("language", request.ui_language)]
    selected = next((item for item in candidates if item.reviewed_on), candidates[0] if candidates else None)
    return render(request, "pms/markets/source.html", {
        "source": source, "translations": translations, "selected_translation": selected, "newer": newer,
        **context,
    })


@market_view
@require_safe
def evidence_detail(request, pk, code, source_pk):
    source = registration_source(request, pk, code, source_pk)
    return source_page(request, source, market=code,
                       can_translate=source.scope != "EU" or not svc.scoped(request.user))


@market_view
@require_http_methods(["GET", "HEAD", "POST"])
@transaction.atomic
def translation_new(request, pk, code, source_pk):
    source = registration_source(request, pk, code, source_pk)
    if source.scope == "EU" and svc.scoped(request.user):
        raise Http404
    if request.method == "POST":
        MedicalDevice.objects.select_for_update().get(pk=pk)
    row = MarketTranslation(original=source, created_by=request.user)
    form = TranslationForm(request.POST if request.method == "POST" else None, instance=row, lang=request.ui_language)
    if request.method == "POST" and form.is_valid():
        row = form.save(commit=False)
        row.version = (source.translations.filter(language=row.language).aggregate(latest=Max("version"))["latest"] or 0) + 1
        if form.cleaned_data["verified"]:
            row.reviewer, row.reviewed_on = request.user, timezone.localdate()
        row.save()
        audit(request.user, "MARKET_TRANSLATION_VERSION", row,
              after={"source": source.pk, "language": row.language, "version": row.version, "reviewed": bool(row.reviewer_id)})
        return redirect("market-evidence", pk, code, source.pk)
    return form_page(request, form, "new_translation", market=code, device=source.device)


@market_view
@require_safe
def case_detail(request, pk):
    case = complaint_for(request, pk)
    entries = svc.case_markets(request.user).filter(complaint=case).order_by("market")
    return render(request, "pms/markets/case.html", {
        "case": case, "entries": entries,
        "available": [code for code in svc.allowed_markets(request.user) if code in COUNTRIES]
        if not svc.scoped(request.user) else (),
    })


def case_entry(request, pk, code):
    country(request, code, unknown=True)
    return get_object_or_404(svc.case_markets(request.user), complaint_id=pk, market=code)


@market_view
@require_http_methods(["GET", "HEAD", "POST"])
@transaction.atomic
def case_country(request, pk, code):
    country(request, code, unknown=True)
    case = complaint_for(request, pk, lock=request.method == "POST")
    entry = svc.case_markets(request.user).filter(complaint=case, market=code).first()
    if not entry and (svc.scoped(request.user) or code == "XX"):
        raise Http404
    if request.method == "POST" and case.status == "CLOSED":
        raise PermissionDenied
    entry = entry or CaseMarket(complaint=case, market=code)
    def state():
        return {name: str(getattr(entry, name) or "") for name in CaseMarketForm.Meta.fields} | {"market": code}

    before = state()
    form = CaseMarketForm(request.POST if request.method == "POST" else None, instance=entry,
                          lang=request.ui_language, actor=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request.user, "MARKET_CASE", entry, before=before, after=state())
        return redirect("market-case-country", pk, code)
    history = entry.assessments.all() if entry.pk else []
    latest = history.first() if entry.pk else None
    evidence = svc.evidence_for(entry)
    registration = matching_registration(entry)
    return render(request, "pms/markets/case_country.html", {
        "entry": entry, "case": case, "market": code, "form": form, "groups": evidence, "registration": registration,
        "history": history[:30], "latest": latest,
        "stale": svc.historical_inputs_changed(entry, latest, evidence, registration),
        "eu_pending": not svc.check_eu(entry, registration, evidence),
        "report_form": LanguageForm(lang=request.ui_language, initial={"language": entry.report_language}),
    })


@market_view
@require_POST
def evaluate(request, pk, code):
    entry = case_entry(request, pk, code)
    svc.assess(entry, request.user)
    return redirect("market-case-country", pk, code)


@market_view
@require_safe
def case_source(request, pk, code, source_pk):
    entry = case_entry(request, pk, code)
    source = get_object_or_404(MarketEvidence, pk=source_pk, device_id=entry.complaint.device_id,
                               scope__in=svc.source_scopes(code), is_example=entry.complaint.is_example)
    return source_page(request, source, market=code, entry=entry)


@market_view
@require_http_methods(["GET", "HEAD", "POST"])
def compare(request, pk, code):
    entry = case_entry(request, pk, code)
    rules = svc.market_rules(request.user, entry)
    results = delta = None
    if request.method == "POST":
        allowed = {str(rule.pk): rule for rule in rules}
        baseline, proposed = (allowed.get(request.POST.get(k)) for k in ("baseline", "proposed"))
        if not baseline or not proposed or baseline.family_key != proposed.family_key or baseline.pk == proposed.pk:
            return render(request, "pms/markets/compare.html", {
                "entry": entry, "rules": rules, "invalid_pair": True,
            }, status=400)
        results, delta = svc.compare(entry, request.user, baseline, proposed)
    return render(request, "pms/markets/compare.html", {
        "entry": entry, "rules": rules, "results": results, "delta": delta,
        "baseline_id": baseline.pk if results else None, "proposed_id": proposed.pk if results else None,
    })


@market_view
@require_http_methods(["GET", "HEAD", "POST"])
def report(request, pk, code):
    entry = case_entry(request, pk, code)
    if request.method == "POST":
        form = LanguageForm(request.POST, lang=request.ui_language)
        if not form.is_valid():
            return form_page(request, form, "report_language", status=400)
        with transaction.atomic():
            CaseMarket.objects.filter(pk=entry.pk).update(report_language=form.cleaned_data["language"])
            audit(request.user, "MARKET_REPORT_DRAFT", entry,
                  after={"language": form.cleaned_data["language"], "market": code})
        return redirect("market-report", pk, code)
    latest = entry.assessments.first()
    evidence = svc.evidence_for(entry)
    registration = matching_registration(entry)
    with translation.override(entry.report_language):
        response = render(request, "pms/markets/report.html", {
            "output_language": entry.report_language, "case": entry.complaint, "entry": entry, "market": code,
            "latest": latest, "current_sources": [svc.source_record(s) for s, _ in evidence],
            "stale": svc.historical_inputs_changed(entry, latest, evidence, registration),
        })
    response["Content-Language"] = entry.report_language
    return response


def legacy_report(request, obj, software):
    output = request.GET.get("language", request.ui_language)
    if output not in CODES:
        raise Http404
    entries = list(svc.case_markets(request.user).filter(complaint=obj.complaint).order_by("market"))
    previous = obj.complaint.rule_applications.select_related("rule").order_by("-pk").first()
    from .market_codes import market_code
    requested = request.GET.get("market")
    entry = next((entry for entry in entries if entry.market == requested), None) if requested else None
    if requested and entry is None:
        raise Http404
    latest = entry.assessments.first() if entry else None
    evidence = svc.evidence_for(entry) if entry else []
    registration = matching_registration(entry) if entry else None
    old_jurisdiction = previous.snapshot.get("rule", {}).get("jurisdiction", previous.rule.jurisdiction) if previous else ""
    market = entry.market if entry else market_code(old_jurisdiction)
    if market not in (*COUNTRIES, "XX"):
        market = "XX"
    audit(request.user, "REPORT_GENERATE", obj, after={"language": output, "market": market})
    with translation.override(output):
        response = render(request, "pms/markets/report.html", {
            "output_language": output, "item": obj, "case": obj.complaint, "entries": entries,
            "legacy": previous if entry is None else entry.legacy_application, "market": market,
            "entry": entry, "latest": latest, "current_sources": [svc.source_record(s) for s, _ in evidence],
            "stale": entry and svc.historical_inputs_changed(entry, latest, evidence, registration),
            "software": software,
        })
    response["Content-Language"] = output
    return response
