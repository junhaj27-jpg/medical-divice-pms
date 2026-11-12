from datetime import date

from django import forms
from django.db import transaction
from django.db.models import Max
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .market_forms import LocalizedForm
from .market_models import GuidanceApplicabilityReview, MarketEvidence, ProductMarket
from .market_service import market_access
from .market_views import device_for, market_view
from .services import audit


REFERENCE_KEY = "fda-dental-curing-lights"
TITLE = "Dental Curing Lights – Premarket Notification (510(k)) Submissions"
OFFICIAL_URL = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/dental-curing-lights-premarket-notification-510k-submissions"
CHECKED_ON = date(2026, 11, 12)
DOCUMENT = {
    "pdf_url": "https://www.fda.gov/media/74206/download",
    "issued_on": "2026-09-02",
    "status": "fda_guidance_final",
    "product_code": "EBZ",
    "regulation_number": "21 CFR 872.6070",
    "docket": "FDA-2024-D-2512",
}


class ApplicabilityForm(LocalizedForm, forms.Form):
    applicability = forms.ChoiceField(choices=[("", ""), *GuidanceApplicabilityReview.DECISIONS])
    applicability_reason = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))


@market_view
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def guidance(request, pk):
    form = ApplicabilityForm(lang=request.ui_language)
    if request.method == "POST":
        with transaction.atomic():
            device = device_for(request, pk, lock=True)
            if not market_access(request.user, ("US",), device):
                raise Http404
            series = device.market_evidence.filter(scope="US", reference_key=REFERENCE_KEY)
            source = series.filter(document_type=MarketEvidence.FDA_GUIDANCE).order_by("-version").first()
            action = request.POST.get("action")
            if action == "link":
                if not source:
                    registration = ProductMarket.objects.filter(device=device, market="US").first()
                    source, created = device.market_evidence.get_or_create(
                        scope="US", reference_key=REFERENCE_KEY, version=(series.aggregate(latest=Max("version"))["latest"] or 0) + 1,
                        defaults={"title": TITLE, "official_url": OFFICIAL_URL, "checked_on": CHECKED_ON,
                                  "language": "en", "clause": "II. Scope", "created_by": request.user,
                                  "excerpt": "Dental curing lights for photopolymerizing restorative resins, including "
                                             "broad-beam and monochromatic sources under 21 CFR 872.6070. "
                                             "Polymerization lasers and tooth-bleaching-only devices are excluded.",
                                  "is_example": bool(registration and registration.is_example),
                                  "document_type": MarketEvidence.FDA_GUIDANCE, "document_metadata": DOCUMENT},
                    )
                    if created:
                        audit(request.user, "FDA_GUIDANCE_LINKED", source, after={"device_id": pk, "version": source.version})
                return redirect("market-product-fda-guidance", pk)
            if action != "review":
                return HttpResponseBadRequest()
            if not source:
                raise Http404
            form = ApplicabilityForm(request.POST, lang=request.ui_language)
            if form.is_valid():
                event = source.applicability_reviews.create(
                    decision=form.cleaned_data["applicability"], rationale=form.cleaned_data["applicability_reason"],
                    reviewer=request.user,
                )
                audit(request.user, "FDA_GUIDANCE_REVIEWED", source, after={
                    "review_id": event.pk, "decision": event.decision, "rationale": event.rationale,
                    "reviewed_at": event.reviewed_at.isoformat(),
                })
                return redirect("market-product-fda-guidance", pk)
    else:
        device = device_for(request, pk)
        if not market_access(request.user, ("US",), device):
            raise Http404
        source = device.market_evidence.filter(scope="US", reference_key=REFERENCE_KEY,
                                               document_type=MarketEvidence.FDA_GUIDANCE).order_by("-version").first()
    reviews = list(source.applicability_reviews.select_related("reviewer")) if source else []
    return render(request, "pms/markets/fda_guidance.html", {
        "device": device, "title": source.title if source else TITLE,
        "official_url": source.official_url if source else OFFICIAL_URL,
        "checked_on": source.checked_on if source else CHECKED_ON,
        "document": source.document_metadata if source else DOCUMENT,
        "source": source, "reviews": reviews, "current": reviews[0] if reviews else None, "form": form,
    }, status=400 if request.method == "POST" else 200)
