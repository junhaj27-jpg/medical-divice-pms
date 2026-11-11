import re
from urllib.parse import parse_qs, urlsplit

from django import forms
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_safe

from .market_forms import LocalizedForm
from .market_i18n import label
from .market_models import EU_COUNTRIES, HarmonisedStandardReview
from .market_service import eu_access, product_markets
from .market_views import device_for, market_view
from .models import MedicalDevice
from .services import audit


COMMISSION = "https://single-market-economy.ec.europa.eu/single-market/goods/european-standards/"
OFFICIAL_LISTS = (
    ("hs_all_lists", COMMISSION + "harmonised-standards_en"),
    ("MDR", COMMISSION + "harmonised-standards/medical-devices_en"),
    ("IVDR", COMMISSION + "harmonised-standards/iv-diagnostic-medical-devices_en"),
)
OFFICIAL_FIELDS = ("edition", "eurlex_url", "decision_number", "decision_item")
PRODUCT_FIELDS = ("applicability", "applicability_reason")


class StandardReviewForm(LocalizedForm, forms.ModelForm):
    class Meta:
        model = HarmonisedStandardReview
        fields = ("regulation", "standard_number", *OFFICIAL_FIELDS, *PRODUCT_FIELDS, "review_date")
        widgets = {"applicability_reason": forms.Textarea(attrs={"rows": 3})}

    def clean_standard_number(self):
        return " ".join(self.cleaned_data["standard_number"].upper().split())

    def clean_eurlex_url(self):
        value = self.cleaned_data["eurlex_url"]
        parts = urlsplit(value)
        query = parse_qs(parts.query, keep_blank_values=True)
        celex = query.get("uri", [])
        valid_eli = not parts.query and re.fullmatch(
            r"/eli/dec_impl/\d{4}/\d+(?:/\d{4}-\d{2}-\d{2})?(?:/oj)?(?:/[a-z]{2,3})?/?", parts.path,
        )
        valid_celex = (re.fullmatch(r"/legal-content/[a-zA-Z]{2}/TXT(?:/PDF)?/?", parts.path)
                       and set(query) == {"uri"} and len(celex) == 1
                       and re.fullmatch(r"CELEX:[03]\d{4}D\d{4}(?:-\d{8})?", celex[0]))
        if (parts.scheme != "https" or parts.netloc != "eur-lex.europa.eu" or "#" in value
                or not (valid_eli or valid_celex)):
            raise forms.ValidationError(label("hs_url_error", self.lang))
        return value


@market_view
@require_safe
def standards(request):
    if not eu_access(request.user):
        raise Http404
    registrations = product_markets(request.user).filter(market__in=EU_COUNTRIES)
    products = MedicalDevice.objects.filter(pk__in=registrations.values("device_id")).order_by("name", "pk")
    page = Paginator(products, 20).get_page(request.GET.get("page"))
    return render(request, "pms/markets/harmonised_standards.html", {"official_lists": OFFICIAL_LISTS, "page": page})


@market_view
@require_http_methods(["GET", "HEAD", "POST"])
def product_reviews(request, pk):
    device = device_for(request, pk)
    if not eu_access(request.user, device):
        raise Http404
    form = StandardReviewForm(request.POST if request.method == "POST" else None, lang=request.ui_language)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            device = device_for(request, pk, lock=True)
            if not eu_access(request.user, device):
                raise Http404
            entry = form.save(commit=False)
            entry.device = device
            entry.reviewer = request.user
            entry.save()
            audit(request.user, "EU_STANDARD_REVIEW", entry, after={
                "device_id": device.pk, "regulation": entry.regulation, "standard_number": entry.standard_number,
                "edition": entry.edition, "applicability": entry.applicability,
            })
        return redirect("market-product-standards", pk)

    reviews = device.harmonised_reviews.all()
    previous = reviews.filter(regulation=OuterRef("regulation"), standard_number=OuterRef("standard_number"),
                              pk__lt=OuterRef("pk")).values("pk")[:1]
    page = Paginator(reviews.select_related("reviewer").annotate(previous_id=Subquery(previous)), 20).get_page(
        request.GET.get("page"),
    )
    older = reviews.in_bulk({entry.previous_id for entry in page if entry.previous_id})
    for entry in page:
        entry.previous = older.get(entry.previous_id)
        if entry.previous:
            entry.changes = [(field, getattr(entry.previous, field), getattr(entry, field))
                             for field in (*OFFICIAL_FIELDS, *PRODUCT_FIELDS)
                             if getattr(entry.previous, field) != getattr(entry, field)]
    return render(request, "pms/markets/harmonised_product.html", {"device": device, "form": form, "page": page},
                  status=400 if request.method == "POST" else 200)
