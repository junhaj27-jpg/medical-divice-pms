import csv
from urllib.parse import urlencode
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .analysis import HEADERS, AnalysisFilter, analyze, csv_cell, default_filters, ingest, require_analyst, save_review
from .analysis_models import AnalysisImport, AnalysisReview
from .analysis_reporting import analysis_pdf


class ImportForm(forms.Form):
    file = forms.FileField(label='UTF-8 CSV')
    is_example = forms.BooleanField(label='샘플 데이터', required=False)


@login_required
def dashboard(request):
    require_analyst(request.user)
    upload_form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and upload_form.is_valid():
        try:
            batch = ingest(upload_form.cleaned_data['file'], request.user, upload_form.cleaned_data['is_example'])
            return redirect('analysis-import', pk=batch.pk)
        except ValidationError as exc: upload_form.add_error(None, exc)
    form = AnalysisFilter(request.GET if request.GET else default_filters())
    result = analyze(form.cleaned_data) if form.is_valid() else None
    if request.GET.get('format') == 'pdf':
        if not result: return HttpResponseBadRequest('필터 오류: 내보내기를 중단했습니다.')
        try:
            content = analysis_pdf(form.cleaned_data, result)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            response = HttpResponse(content, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="pms-analysis.pdf"'
            return response
    if request.GET.get('format') == 'csv':
        if not result: return HttpResponseBadRequest('필터 오류: 내보내기를 중단했습니다.')
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="pms-filtered.csv"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow(['analysis_id', 'batch_id', 'row_number', 'data_kind'] + HEADERS)
        for row in result['records']:
            writer.writerow([row.pk, row.batch_id, row.row_number, form.cleaned_data['example']] + [csv_cell(getattr(row, key)) for key in HEADERS])
        return response
    return render(request, 'pms/analysis.html', {
        'form': form, 'upload_form': upload_form, 'result': result,
        'users': User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(profile__role__in=['RA_QA', 'ADMIN'])),
        'statuses': AnalysisReview._meta.get_field('status').choices,
        'query': request.GET.urlencode(), 'batches': AnalysisImport.objects.order_by('-pk')[:10],
        'report': request.GET.get('format') == 'report',
        'saved_reviews': AnalysisReview.objects.select_related('assignee').order_by('-updated_at')[:20],
    })


@login_required
def import_detail(request, pk):
    require_analyst(request.user)
    batch = get_object_or_404(AnalysisImport, pk=pk)
    filters = default_filters()
    filters['example'] = 'sample' if batch.is_example else 'real'
    return render(request, 'pms/analysis_import.html', {'batch': batch, 'analysis_query': urlencode(filters)})


@login_required
def review_detail(request, pk):
    require_analyst(request.user)
    saved = get_object_or_404(AnalysisReview.objects.select_related('assignee'), pk=pk)
    return render(request, 'pms/analysis_review.html', {'review': saved})


@login_required
@require_POST
def review(request):
    require_analyst(request.user)
    form = AnalysisFilter(request.GET)
    if not form.is_valid(): return HttpResponseBadRequest('필터 오류')
    signal = next((s for s in analyze(form.cleaned_data)['signals'] if s['key'] == request.POST.get('key')), None)
    if signal is None: return HttpResponseBadRequest('데이터가 변경되었거나 신호가 없습니다. 다시 분석하세요.')
    try:
        assignee = User.objects.get(pk=request.POST.get('assignee'), is_active=True)
        save_review(request.user, signal, request.POST.get('status'), assignee, request.POST.get('note', ''))
    except (User.DoesNotExist, ValueError, TypeError, ValidationError) as exc:
        messages.error(request, '검토 저장 실패: ' + ('; '.join(exc.messages) if isinstance(exc, ValidationError) else '담당자를 확인하세요.'))
    else: messages.success(request, '검토 결과와 인증된 사용자 이력을 저장했습니다.')
    return redirect('/analysis/?' + request.GET.urlencode())
