"""Language selection is presentation-only; market codes and stored dates stay stable."""
import logging
from functools import lru_cache
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin

from .market_models import LANGUAGES

LOG = logging.getLogger("pms.i18n")
DEFAULT = "ko-KR"
CODES = [code for code, _ in LANGUAGES]


@lru_cache(maxsize=1)
def catalog():
    rows = {}
    for line in Path(__file__).with_name("market_strings.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, *values = line.split("|")
        if len(values) != len(CODES) or key in rows or not values[1]:
            raise ValueError(f"Invalid market UI translation row: {key}")
        rows[key] = dict(zip(CODES, values))
    return rows


def label(key, lang=DEFAULT):
    row = catalog().get(key, {})
    if row.get(lang):
        return row[lang]
    LOG.warning("Missing UI translation: locale=%s key=%s", lang, key)
    return row.get("en") or str(key).replace("_", " ")


def ui_context(request):
    from .market_service import allowed_markets, scoped
    return {
        "ui_language": getattr(request, "ui_language", DEFAULT),
        "ui_languages": LANGUAGES,
        "market_scoped": scoped(request.user),
        "market_workspace": bool(allowed_markets(request.user)),
    }


class MarketLocaleMiddleware(MiddlewareMixin):
    def __call__(self, request):
        language = getattr(getattr(request.user, "profile", None), "ui_language", DEFAULT)
        request.ui_language = language if language in CODES else DEFAULT
        with translation.override(request.ui_language):
            response = super().__call__(request)
        response.headers.setdefault("Content-Language", request.ui_language)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        from .market_service import scoped
        if not scoped(request.user):
            return None
        # Legacy routes do not all enforce country grants, including indirect evidence,
        # API, and task routes. Country-scoped accounts use the workspace allowlist.
        match = request.resolver_match
        if (match.url_name or "").startswith("market-") or match.url_name in ("login", "logout", "password_change", "password_change_done"):
            return None
        if match.url_name == "dashboard":
            from django.shortcuts import redirect
            return redirect("market-dashboard")
        return denied(request, PermissionDenied())

    def process_exception(self, request, exception):
        name = request.resolver_match.url_name or "" if request.resolver_match else ""
        if name.startswith("market-"):
            if isinstance(exception, Http404):
                return missing(request, exception)
            if isinstance(exception, PermissionDenied):
                return denied(request, exception)
        return None


def localized_error(request, exception, status):
    return render(request, "pms/markets/error.html", {"error": f"error_{status}"}, status=status)


def denied(request, exception):
    return localized_error(request, exception, 403)


def missing(request, exception):
    return localized_error(request, exception, 404)
