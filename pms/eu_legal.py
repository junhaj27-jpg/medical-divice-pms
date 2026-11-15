import re
from urllib.parse import parse_qs, urlencode, urlsplit

from django import forms
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .dental_models import DentalProject
from .eu_legal_models import EULegalDocument, EUProjectLaw, EUApplicabilityReview, EUImpactConfirmation
from .market_forms import LocalizedForm
from .market_i18n import label
from .market_service import eu_access, product_markets, scoped
from .market_models import EU_COUNTRIES
from .market_views import market_view
from .services import audit

TODAY_OJ = "https://eur-lex.europa.eu/TodayOJ/index.html"
LANGUAGES = [(key, key.upper()) for key in ("en", "de", "fr", "es", "it", "nl", "pl", "bg", "cs", "da", "el", "et",
                                           "fi", "ga", "hr", "hu", "lt", "lv", "mt", "pt", "ro", "sk", "sl", "sv")]
CELEX = re.compile(r"[0-9][0-9]{4}[A-Z]{1,3}[0-9]{4,8}(?:\([0-9]{2}\))?(?:R\([0-9]{2}\))?(?:-[0-9]{8})?")


def celex_url(celex, language):
    return f"https://eur-lex.europa.eu/legal-content/{language.upper()}/TXT/?" + urlencode({"uri": "CELEX:" + celex})


def normalize_source(celex, url, language):
    celex = celex.strip().upper().removeprefix("CELEX:")
    if celex and not CELEX.fullmatch(celex):
        raise ValueError
    if not url:
        if not celex:
            raise ValueError
        return celex, celex_url(celex, language), celex
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != "eur-lex.europa.eu" or parts.fragment:
        raise ValueError
    if re.fullmatch(r"/legal-content/[A-Za-z]{2}/TXT(?:/PDF)?/?", parts.path):
        query = parse_qs(parts.query)
        if set(query) - {"uri", "qid"} or len(query.get("uri", [])) != 1:
            raise ValueError
        uri = query["uri"][0]
        if not uri.upper().startswith("CELEX:"):
            raise ValueError
        from_url = uri[6:].upper()
        if not CELEX.fullmatch(from_url) or (celex and celex != from_url):
            raise ValueError
        return from_url, celex_url(from_url, language), from_url
    if re.fullmatch(r"/eli/[a-z_]+/[0-9]{4}/[0-9]+(?:/[A-Za-z0-9_-]+)*/?", parts.path) and not parts.query:
        root = re.match(r"/eli/(reg|dir|dec)/([0-9]{4})/([0-9]+)/oj(?:/[a-z]{3})?/?$", parts.path)
        if root:
            inferred = "3" + root[2] + {"reg": "R", "dir": "L", "dec": "D"}[root[1]] + root[3].zfill(4)
            if celex and celex != inferred:
                raise ValueError
            return inferred, celex_url(inferred, language), inferred
        if celex:
            return celex, celex_url(celex, language), celex
        return parts.path.rstrip("/"), url, ""
    raise ValueError


class DocumentForm(LocalizedForm, forms.ModelForm):
    celex = forms.CharField(required=False, max_length=60)
    official_url = forms.URLField(required=False, max_length=1000)
    language = forms.CharField()

    class Meta:
        model = EULegalDocument
        fields = ("celex", "official_url", "title", "source_type", "kind", "parent", "oj_reference",
                  "published_on", "effective_on", "applies_on", "language", "checked_on")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["language"] = forms.ChoiceField(choices=LANGUAGES, label=label("language", self.lang))
        self.fields["effective_on"].label = label("eu_effective_on", self.lang)

    def clean(self):
        data = super().clean()
        if "language" not in data:
            return data
        try:
            identity, url, celex = normalize_source(data.get("celex", ""), data.get("official_url", ""), data["language"])
        except ValueError:
            self.add_error("official_url", label("eu_document_url_error", self.lang))
        else:
            data["identifier"], data["official_url"], data["celex"] = identity, url, celex
            self.instance.identifier = identity
        if data.get("parent") and data.get("kind") == "eu_oj":
            self.add_error("kind", label("invalid", self.lang))
        return data


def projects_for(user):
    projects = DentalProject.objects.filter(market="EU").select_related("device", "template")
    if scoped(user):
        projects = projects.filter(device_id__in=product_markets(user).filter(market__in=EU_COUNTRIES).values("device_id"))
    return projects


def law_snapshot(project):
    rows = []
    for link in project.legal_links.select_related("document").prefetch_related("reviews").order_by("pk"):
        doc = link.document
        review = link.reviews.first()
        rows.append({"id": link.pk, "section": link.section, "document_id": doc.pk, "celex": doc.celex,
                     "title": doc.title, "source_type": doc.source_type, "kind": doc.kind,
                     "url": doc.official_url, "clause": link.clause, "language": doc.language,
                     "published_on": str(doc.published_on or ""), "effective_on": str(doc.effective_on or ""),
                     "applies_on": str(doc.applies_on or ""), "checked_on": str(doc.checked_on),
                     "decision": review.decision if review else "eu_pending", "reason": review.reason if review else "",
                     "review_id": review.pk if review else None})
    return rows


def eu_context(project, user):
    from .dental_workflow import template_items
    laws = list(EULegalDocument.objects.all())
    links = []
    for link in project.legal_links.select_related("document").order_by("pk"):
        link.latest = link.reviews.select_related("actor").first()
        links.append(link)
    return {"eu_documents": laws, "eu_links": links, "eu_sections": template_items(project)}


def update_project_law(project, request):
    section = request.POST.get("section", "")
    if request.POST.get("action") == "law_link":
        from .dental_workflow import template_items
        if section not in {item["id"] for item in template_items(project)}:
            raise Http404
        pk = request.POST.get("document_id", "")
        if not re.fullmatch(r"[0-9]{1,18}", pk):
            raise Http404
        doc = get_object_or_404(EULegalDocument, pk=pk)
        clause = request.POST.get("clause", "").strip()
        if not clause or len(clause) > 240:
            return label("eu_clause_required", request.ui_language)
        link, created = project.legal_links.get_or_create(section=section, document=doc, clause=clause,
                                                         defaults={"actor": request.user})
        if created:
            audit(request.user, "EU_LAW_LINK", link, after={"document_id": doc.pk, "section": section})
    else:
        pk = request.POST.get("link_id", "")
        if not re.fullmatch(r"[0-9]{1,18}", pk):
            raise Http404
        link = get_object_or_404(project.legal_links.select_for_update(), pk=pk)
        decision, reason = request.POST.get("decision"), request.POST.get("reason", "").strip()
        previous = request.POST.get("previous", "")
        latest = link.reviews.first()
        if previous != str(latest.pk if latest else 0):
            return label("comparison_review_conflict", request.ui_language)
        if decision not in ("hs_applies", "hs_does_not_apply", "eu_pending") or not reason or len(reason) > 2000:
            return label("eu_reason_required", request.ui_language)
        review = link.reviews.create(decision=decision, reason=reason, actor=request.user)
        audit(request.user, "EU_LAW_REVIEW", link, after={"review_id": review.pk, "decision": decision})
    return ""


@market_view
@never_cache
@require_http_methods(["GET", "POST"])
def documents(request, pk=None):
    if not eu_access(request.user):
        raise Http404
    doc = get_object_or_404(EULegalDocument, pk=pk) if pk else None
    message = "eu_lookup_manual" if request.method == "POST" and request.POST.get("action") == "lookup" else ""
    form = DocumentForm(request.POST if request.method == "POST" and request.POST.get("action") == "register" else None,
                        lang=request.ui_language, initial={"language": "en", "checked_on": timezone.localdate()})
    if request.method == "POST" and request.POST.get("action") == "register" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            values = {key: value for key, value in data.items() if key not in ("identifier", "language")}
            record, created = EULegalDocument.objects.get_or_create(identifier=data["identifier"], language=data["language"],
                                                                   defaults={**values, "recorded_by": request.user})
            if created:
                audit(request.user, "EU_DOCUMENT_REGISTER", record, after={"identifier": record.identifier, "kind": record.kind})
        return redirect("market-eu-document", record.pk)
    candidates = []
    if doc and doc.parent_id:
        candidates = list(EUProjectLaw.objects.filter(document_id=doc.parent_id, project__in=projects_for(request.user))
                          .select_related("project__device", "project__template"))
    if doc and request.method == "POST" and request.POST.get("action") == "confirm_impact":
        selected = request.POST.getlist("link")
        available = {str(link.pk): link for link in candidates}
        reason = request.POST.get("reason", "").strip()
        if not selected or any(pk not in available for pk in selected):
            raise Http404
        if not reason or len(reason) > 2000:
            message = "eu_reason_required"
        else:
            with transaction.atomic():
                for pk in dict.fromkeys(selected):
                    link = available[pk]
                    event, created = EUImpactConfirmation.objects.get_or_create(
                        project=link.project, section=link.section, document=doc, defaults={"actor": request.user, "reason": reason})
                    if created:
                        audit(request.user, "EU_IMPACT_CONFIRMED", event, after={"section": link.section, "document_id": doc.pk})
            return redirect("market-eu-document", doc.pk)
    language_links = [(lang, celex_url(doc.celex, lang)) for lang, _ in LANGUAGES] if doc and doc.celex else []
    confirmations = (EUImpactConfirmation.objects.filter(document=doc, project__in=projects_for(request.user))
                     .select_related("actor", "project__device").order_by("-pk")) if doc else []
    return render(request, "pms/markets/eu_documents.html", {
        "document": doc, "form": form, "today_oj": TODAY_OJ, "message": message, "candidates": candidates,
        "language_links": language_links, "confirmations": confirmations,
        "page": Paginator(EULegalDocument.objects.select_related("parent"), 30).get_page(request.GET.get("page")),
    }, status=400 if request.method == "POST" and request.POST.get("action") == "register" else 200)
