import json

from django import forms
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from . import market_review as review
from .market_views import case_entry, market_view


class ReviewForm(forms.Form):
    note = forms.CharField(max_length=2000)
    complete = forms.BooleanField(required=False)
    previous = forms.IntegerField(min_value=0)


@market_view
@never_cache
@require_safe
def comparison_run(request, pk):
    run = get_object_or_404(review.runs_for(request.user), pk=pk)
    results = list(run.results.annotate(latest_id=review.latest_review_id()))
    events = review.MarketComparisonReview.objects.in_bulk([r.latest_id for r in results if r.latest_id])
    flag = request.GET.get("change", "")
    flag = flag if flag in review.FILTERS else ""
    rows = [r.snapshot | {"result_id": r.pk, "review_status": review.review_status(r, events.get(r.latest_id))}
            for r in results if not flag or flag in r.snapshot["changes"]]
    return render(request, "pms/markets/comparison_run.html", {
        "run": run, "rows": rows, "change": flag, "filters": review.FILTERS,
    })


@market_view
@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def comparison_result(request, pk, api=False):
    result = get_object_or_404(
        review.MarketComparisonResult.objects.filter(run__in=review.runs_for(request.user).order_by())
        .select_related("run__actor", "entry"), pk=pk,
    )
    error = None
    status = 200
    if request.method == "POST":
        data = request.POST
        if api:
            try:
                data = json.loads(request.body) if len(request.body) <= 16_384 else None
            except (ValueError, UnicodeError):
                data = None
            if not isinstance(data, dict) or not isinstance(data.get("note"), str) or type(data.get("complete")) is not bool:
                return JsonResponse({"error": "comparison_note_error"}, status=400)
        form = ReviewForm(data)
        if not form.is_valid():
            error, status = "comparison_note_error", 400
        elif not review.record_review(result, request.user, **form.cleaned_data):
            error, status = "comparison_review_conflict", 409
        elif not api:
            return redirect("market-comparison-result", pk)
    events = list(result.reviews.select_related("actor"))
    latest = events[0] if events else None
    state = review.review_status(result, latest)
    if api:
        return JsonResponse({
            "id": result.pk, "run": result.run_id, "market": result.run.market, "rules": result.run.rules,
            "recorded_at": result.run.recorded_at, "actor": result.run.actor.get_username(),
            "snapshot": result.snapshot, "review_status": state, "revision": latest.pk if latest else 0,
            "reviews": [{"id": e.pk, "at": e.recorded_at, "actor": e.actor.get_username(),
                         "complete": e.complete, "note": e.note} for e in events], "error": error,
        }, status=status)
    return render(request, "pms/markets/comparison_result.html", {
        "result": result, "run": result.run, "row": result.snapshot, "events": events,
        "latest": latest, "review_status": state, "review_error": error,
    }, status=status)


@market_view
@never_cache
@require_safe
def comparison_history(request, pk, code):
    entry = case_entry(request, pk, code)
    comparisons = entry.comparisons.filter(run__in=review.runs_for(request.user).order_by()
                                          ).select_related("run__actor").order_by("-pk")
    from django.core.paginator import Paginator
    page = Paginator(comparisons, 30).get_page(request.GET.get("page"))
    return render(request, "pms/markets/comparison_history.html", {"entry": entry, "page": page})


@market_view
@never_cache
@require_safe
def operating_snapshot(request, pk, code, assessment=None):
    entry = case_entry(request, pk, code)
    if assessment is None:
        legacy = entry.legacy_application
        if not legacy or legacy.complaint_id != entry.complaint_id:
            raise Http404
        return render(request, "pms/markets/operating_snapshot.html", {
            "entry": entry, "market": code, "legacy": legacy,
        })
    record = get_object_or_404(entry.assessments.select_related("actor"), pk=assessment)
    return render(request, "pms/markets/operating_snapshot.html", {
        "entry": entry, "case": entry.complaint, "market": code, "record": record,
    })
