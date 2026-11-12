import re
from urllib.parse import urlencode, urlsplit

from django import forms
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe
from django.utils.dateparse import parse_date

from .fda_classification import LookupError, fetch_results
from .market_forms import LocalizedForm
from .market_i18n import label
from .market_models import FDA510kReview
from .market_service import market_access, product_markets
from .market_views import device_for, market_view
from .models import MedicalDevice
from .services import audit


FDA_SEARCH = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm"
FDA_API = "https://api.fda.gov/device/510k.json"
FDA_DETAIL = "https://www.accessdata.fda.gov/SCRIPTS/cdrh/devicesatfda/index.cfm"
SOURCE_FIELDS = ("k_number", "fda_device_name", "applicant_name", "product_code", "decision_date",
                 "fda_decision", "fda_detail_url")
COMPARE_FIELDS = (*SOURCE_FIELDS, "purpose", "review_opinion")


class CaseLookupForm(LocalizedForm, forms.Form):
    search_field = forms.ChoiceField(choices=[("product_code", ""), ("k_number", "")])
    search_term = forms.CharField(max_length=7)

    def clean(self):
        data = super().clean()
        term, field = data.get("search_term", "").upper(), data.get("search_field")
        if term and field and not re.fullmatch(r"K[0-9]{6}" if field == "k_number" else r"[A-Z0-9]{3}", term):
            self.add_error("search_term", label("invalid", self.lang))
        else:
            data["search_term"] = term
        return data


def case_results(field, term):
    rows = []
    for raw in fetch_results(FDA_API, field, term):
        number = raw.get("k_number")
        if not isinstance(number, str) or not re.fullmatch(r"K[0-9]{6}", number):
            continue
        row = {target: raw.get(source) if isinstance(raw.get(source), str) else ""
               for target, source in zip(SOURCE_FIELDS, ("k_number", "device_name", "applicant", "product_code",
                                                         "decision_date", "decision_description"))}
        try:
            row["decision_date"] = parse_date(row["decision_date"])
        except ValueError:
            row["decision_date"] = None
        row["fda_detail_url"] = FDA_DETAIL + "?" + urlencode({"db": "pmn", "id": number})
        row["selection"] = urlencode({"search_field": field, "search_term": term, "selected": number})
        rows.append(row)
    return rows


class FDAReviewForm(LocalizedForm, forms.ModelForm):
    class Meta:
        model = FDA510kReview
        fields = (*SOURCE_FIELDS, "purpose", "review_opinion", "previous")
        widgets = {"review_opinion": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, device, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["previous"].queryset = device.fda_510k_reviews.all()

    def clean_k_number(self):
        number = self.cleaned_data["k_number"].upper()
        if not re.fullmatch(r"K[0-9]{6}", number):
            raise forms.ValidationError(label("fda_k_error", self.lang))
        return number

    def clean_product_code(self):
        code = self.cleaned_data["product_code"].upper()
        if not re.fullmatch(r"[A-Z0-9]{3}", code):
            raise forms.ValidationError(label("invalid", self.lang))
        return code

    def clean_fda_detail_url(self):
        value = self.cleaned_data["fda_detail_url"]
        parts = urlsplit(value)
        expected = urlsplit(FDA_SEARCH)
        path = parts.path.lower()
        if path == expected.path.lower():
            pattern = r"id=(K[0-9]{6})"
        elif path == "/scripts/cdrh/devicesatfda/index.cfm":
            pattern = r"db=pmn&id=(K[0-9]{6})|id=(K[0-9]{6})&db=pmn"
        else:
            pattern = r"(?!)"
        match = re.fullmatch(pattern, parts.query, re.IGNORECASE | re.ASCII)
        linked_number = next((group for group in match.groups() if group), "").upper() if match else ""
        number = self.cleaned_data.get("k_number")
        if (parts.scheme != "https" or parts.netloc.lower() != expected.netloc
                or "#" in value or not linked_number or (number and linked_number != number)):
            raise forms.ValidationError(label("fda_url_error", self.lang))
        return value


@market_view
@require_safe
def fda_search(request):
    if not market_access(request.user, ("US",)):
        raise Http404
    registrations = product_markets(request.user).filter(market="US")
    products = MedicalDevice.objects.filter(pk__in=registrations.values("device_id")).order_by("name", "pk")
    page = Paginator(products, 20).get_page(request.GET.get("page"))
    return render(request, "pms/markets/fda_search.html", {"fda_search_url": FDA_SEARCH, "page": page})


@market_view
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def fda_product_reviews(request, pk):
    device = device_for(request, pk)
    if not market_access(request.user, ("US",), device):
        raise Http404
    code = request.GET.get("product_code", "").upper()
    code = code if re.fullmatch(r"[A-Z0-9]{3}", code) else ""
    lookup_form = CaseLookupForm(request.GET if "search_term" in request.GET else None, lang=request.ui_language,
                                 initial={"search_field": "product_code", "search_term": code})
    results, message, selected = [], "", None
    if request.method == "GET" and lookup_form.is_bound and lookup_form.is_valid():
        try:
            results = case_results(lookup_form.cleaned_data["search_field"], lookup_form.cleaned_data["search_term"])
        except LookupError:
            message = "fda_lookup_failed"
        else:
            if not results:
                message = "fda_no_matches"
            selected = next((row for row in results if row["k_number"] == request.GET.get("selected")), None)
    form = FDAReviewForm(request.POST if request.method == "POST" else None, lang=request.ui_language, device=device,
                         initial={key: selected[key] for key in SOURCE_FIELDS} if selected else {"product_code": code})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            device = device_for(request, pk, lock=True)
            if not market_access(request.user, ("US",), device):
                raise Http404
            entry = form.save(commit=False)
            entry.device = device
            entry.reviewer = request.user
            existing = device.fda_510k_reviews.filter(k_number=entry.k_number, purpose=entry.purpose,
                                                       previous_id=entry.previous_id).first()
            if existing:
                return redirect(f"{request.path}?existing={existing.pk}#review-{existing.pk}")
            entry.save()
            audit(request.user, "FDA_510K_REVIEW", entry, after={
                "device_id": device.pk, "k_number": entry.k_number, "purpose": entry.purpose,
                "previous_id": entry.previous_id,
            })
        return redirect("market-product-fda-510k", pk)

    reviews = device.fda_510k_reviews.select_related("reviewer", "previous")
    page = Paginator(reviews, 20).get_page(request.GET.get("page"))
    for entry in page:
        if entry.previous:
            entry.changes = [(field, getattr(entry.previous, field), getattr(entry, field))
                             for field in COMPARE_FIELDS if getattr(entry.previous, field) != getattr(entry, field)]
    return render(request, "pms/markets/fda_product.html", {"device": device, "form": form, "page": page,
                  "lookup_code": code, "fda_search_url": FDA_SEARCH, "lookup_form": lookup_form,
                  "results": results, "message": message, "selected": selected,
                  "existing": reviews.filter(pk=request.GET["existing"]).first()
                  if re.fullmatch(r"[0-9]{1,18}", request.GET.get("existing", "")) else None},
                  status=400 if request.method == "POST" else 200)
