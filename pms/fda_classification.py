import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django import forms
from django.core import signing
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .market_forms import LocalizedForm
from .market_i18n import label
from .market_models import FDAClassificationEvidence
from .market_service import market_access
from .market_views import device_for, market_view
from .services import audit


FDA_PAGE = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD/classification.cfm"
API = "https://api.fda.gov/device/classification.json"
TOKEN_SALT = "market-fda-classification"
CODE = re.compile(r"[A-Z0-9]{3}")
FIELDS = ("product_code", "device_name", "device_class", "regulation_number")


class LookupError(Exception):
    pass


class LookupForm(LocalizedForm, forms.Form):
    search_field = forms.ChoiceField(choices=[("product_code", ""), ("device_name", "")])
    search_term = forms.CharField(max_length=120)

    def clean(self):
        data = super().clean()
        term = data.get("search_term")
        if term and data.get("search_field") == "product_code":
            data["search_term"] = term.upper()
            if not CODE.fullmatch(data["search_term"]):
                self.add_error("search_term", label("invalid", self.lang))
        return data


class EvidenceReviewForm(LocalizedForm, forms.Form):
    review_opinion = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))


def fetch_results(endpoint, field, term):
    literal = term.replace("\\", "\\\\").replace('"', '\\"')
    url = endpoint + "?" + urlencode({"search": f'{field}:"{literal}"', "limit": 20})
    try:
        with urlopen(url, timeout=5) as response:
            payload = json.load(response)
    except HTTPError as exc:
        with exc:
            if exc.code == 404:
                try:
                    payload = json.load(exc)
                except (ValueError, OSError):
                    payload = None
                if isinstance(payload, dict) and payload.get("error") == {"code": "NOT_FOUND", "message": "No matches found!"}:
                    return []
        raise LookupError from exc
    except (URLError, OSError, ValueError) as exc:
        raise LookupError from exc
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise LookupError
    return rows


def lookup(field, term):
    return [{key: row[key].strip() if isinstance(row.get(key), str) else "" for key in FIELDS}
            for row in fetch_results(API, field, term)]


@market_view
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def classification(request, pk):
    device = device_for(request, pk)
    if not market_access(request.user, ("US",), device):
        raise Http404
    evidence = device.fda_classifications.all()
    review_form = EvidenceReviewForm(lang=request.ui_language)
    review_id = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            try:
                user_id, device_id, snapshot, retrieved = signing.loads(
                    request.POST.get("snapshot", ""), salt=TOKEN_SALT, max_age=3600,
                )
            except signing.BadSignature:
                return HttpResponseBadRequest(label("fda_lookup_expired", request.ui_language))
            if (user_id, device_id) != (request.user.pk, device.pk):
                raise Http404
            code = snapshot["product_code"]
            with transaction.atomic():
                record, created = device.fda_classifications.get_or_create(product_code=code, defaults={
                    "snapshot": snapshot, "source_url": FDA_PAGE + "?" + urlencode({"ID": code}),
                    "retrieved_at": parse_datetime(retrieved),
                })
                if created:
                    audit(request.user, "FDA_CLASSIFICATION_SAVED", record, after={"product_code": code, "device_id": pk})
            return redirect(f"{request.path}#evidence-{record.pk}")
        if action != "review":
            return HttpResponseBadRequest()
        review_id = request.POST.get("evidence_id", "")
        if not review_id.isascii() or not review_id.isdecimal() or len(review_id) > 18:
            raise Http404
        review_id = int(review_id)
        review_form = EvidenceReviewForm(request.POST, lang=request.ui_language)
        with transaction.atomic():
            record = get_object_or_404(evidence.select_for_update(), pk=review_id)
            if record.reviewed_at:
                return redirect(f"{request.path}#evidence-{record.pk}")
            if review_form.is_valid():
                record.reviewed_at = timezone.now()
                record.reviewer = request.user
                record.review_opinion = review_form.cleaned_data["review_opinion"]
                record.save(update_fields=["reviewed_at", "reviewer", "review_opinion"])
                audit(request.user, "FDA_CLASSIFICATION_REVIEWED", record, before={"status": "pending"}, after={
                    "status": "reviewed", "reviewed_at": record.reviewed_at.isoformat(),
                    "review_opinion": record.review_opinion,
                })
                return redirect(f"{request.path}#evidence-{record.pk}")

    search_form = LookupForm(request.GET if "search_term" in request.GET else None, lang=request.ui_language)
    records = list(evidence.select_related("reviewer"))
    saved = {record.product_code: record.pk for record in records}
    results, message = [], ""
    if request.method == "GET" and search_form.is_bound and search_form.is_valid():
        try:
            rows = lookup(search_form.cleaned_data["search_field"], search_form.cleaned_data["search_term"])
        except LookupError:
            message = "fda_lookup_failed"
        else:
            retrieved = timezone.now().isoformat()
            for row in rows:
                code = row["product_code"].upper()
                result = {"data": row, "source": FDA_PAGE}
                if CODE.fullmatch(code):
                    row["product_code"] = code
                    result.update(code=code, source=FDA_PAGE + "?" + urlencode({"ID": code}), existing=saved.get(code),
                                  token=signing.dumps((request.user.pk, pk, row, retrieved), salt=TOKEN_SALT))
                results.append(result)
            if not results:
                message = "fda_no_matches"
    return render(request, "pms/markets/fda_classification.html", {
        "device": device, "official_url": FDA_PAGE, "search_form": search_form,
        "results": results, "message": message, "records": records, "review_form": review_form, "review_id": review_id,
    }, status=400 if request.method == "POST" else 200)
