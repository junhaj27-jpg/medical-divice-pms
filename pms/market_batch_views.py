from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from . import market_batch as batch
from . import market_service as svc
from .market_codes import market_code
from .market_models import COUNTRIES
from .market_views import country, market_view
from .regulatory import rules_for
from .services import audit


@market_view
@require_http_methods(["GET", "HEAD", "POST"])
def batch_compare(request, code=None):
    markets = [code for code in svc.allowed_markets(request.user) if code in COUNTRIES]
    if code:
        country(request, code)
    context = {"markets": markets, "market": code, "limit": batch.LIMIT}
    if not code:
        if request.method == "POST":
            raise Http404
        return render(request, "pms/markets/batch.html", context)

    # Both selectors and submitted IDs use the existing market and case visibility rules.
    entries = svc.case_markets(request.user).filter(market=code).select_related(
        "complaint__risk_assessment", "complaint__adverse_event",
    ).order_by("-complaint_id")
    rules = {str(rule.pk): rule for rule in rules_for(request.user).order_by("name", "version")
             if market_code(rule.jurisdiction) == code}
    context.update(rules=rules.values(), entries=entries[:batch.LIMIT],
                   more_cases=entries.count() > batch.LIMIT)
    if request.method != "POST":
        return render(request, "pms/markets/batch.html", context)

    entered_ids = request.POST.get("case_ids", "")
    selected = request.POST.getlist("case") + [value.strip() for value in entered_ids.split(",") if value.strip()]
    ids = [request.POST.get(side) for side in batch.SIDES]
    rule_pair = [rules.get(key) for key in ids]
    context.update(selected=selected, entered_ids=entered_ids[:2000], baseline_id=ids[0], proposed_id=ids[1])
    error = None
    if len(entered_ids) > 2000 or not selected or len(selected) > batch.LIMIT or len(set(selected)) != len(selected):
        error = "batch_count_error"
    elif any(not key.isascii() or not key.isdecimal() or len(key) > 19 or not 0 < int(key) <= 2**63 - 1 for key in selected):
        error = "batch_cases_error"
    elif not all(rule_pair) or rule_pair[0].family_key != rule_pair[1].family_key:
        error = "batch_pair_error"
    else:
        available = {str(entry.complaint_id): entry for entry in entries.filter(complaint_id__in=selected)}
        if any(key not in available for key in selected):
            error = "batch_cases_error"
        else:
            rows = batch.run([available[key] for key in selected], rule_pair, request.user, code)
            engines = sorted({engine["name"] for row in rows for engine in row["engines"].values()})
            review = sum("review_required" in row["changes"] for row in rows)
            context.update(rows=rows)
            audit(request.user, "MARKET_RULE_BATCH", after={
                "market": code, "rules": [{"id": r.pk, "version": r.version} for r in rule_pair],
                "engines": engines, "count": len(rows), "review_count": review,
                "status": "review_required" if review else "complete",
            })
    if error:
        context["batch_error"] = error
        audit(request.user, "MARKET_RULE_BATCH", after={
            "market": code, "rules": [{"id": r.pk, "version": r.version} for r in rule_pair if r],
            "engines": [], "count": len(selected), "status": "invalid_input",
        })
    return render(request, "pms/markets/batch.html", context, status=400 if error else 200)

@market_view
@require_http_methods(["GET", "HEAD"])
def offline_demo(request):
    from django.contrib.staticfiles import finders
    from django.shortcuts import redirect
    from django.templatetags.static import static

    if all(finders.find("rule-batch/" + name) for name in ("index.html", "engine.js", "examples.json", "sw.js")):
        return redirect(static("rule-batch/index.html"))
    return render(request, "pms/markets/batch_demo.html")
