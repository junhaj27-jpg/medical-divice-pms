from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .analysis import require_analyst, AnalysisFilter
from .analysis_models import AnalysisArtifact
from .services import visible_complaints
from .internal_cohort import preview_internal, import_internal, confirm_seriousness, internal_payload
from .analysis import digest
from .analysis_archive import generate_analysis_report, analysis_artifact_bytes


@login_required
def internal_import(request):
    require_analyst(request.user)
    qs=visible_complaints(request.user).select_related('device').order_by('pk')
    q=request.GET.get('q','').strip()
    if q:
        criteria=Q(title__icontains=q)|Q(device__name__icontains=q)
        if q.removeprefix('CMP-').isdigit(): criteria|=Q(pk=int(q.removeprefix('CMP-')))
        qs=qs.filter(criteria)
    if request.GET.get('example') in ('0','1'): qs=qs.filter(is_example=request.GET['example']=='1')
    page=Paginator(qs,20).get_page(request.GET.get('page'))
    preview=None; token=''
    try:
        if request.method=='POST':
            if request.POST.get('action')=='import':
                data=signing.loads(request.POST.get('token',''),salt='internal-import',max_age=1800)
                if data['user']!=request.user.pk or request.POST.get('confirmed')!='yes': raise ValidationError('대상과 건수를 명시적으로 확인하세요.')
                created=import_internal(request.user,data['hashes'])
                messages.success(request,f'{len(created)}건의 새 스냅샷을 저장했습니다. 같은 원본 버전은 중복하지 않습니다.')
                return redirect('analysis-internal')
            ids=request.POST.getlist('case_ids')
            if any(not x.isdigit() for x in ids): raise ValidationError('사건번호를 확인하세요.')
            preview=preview_internal(request.user,[int(x) for x in ids])
            token=signing.dumps({'user':request.user.pk,'hashes':{str(r['data']['case_id']):r['hash'] for r in preview}},salt='internal-import')
    except (ValidationError,signing.BadSignature,KeyError) as exc:
        messages.error(request,' / '.join(exc.messages) if isinstance(exc,ValidationError) else '미리보기 유효시간이 지났습니다. 다시 선택하세요.')
    query=request.GET.copy();query.pop('page',None)
    rows=[(c,digest(internal_payload(c))) for c in page]
    return render(request,'pms/analysis_internal.html',{'rows':rows,'page':page,'preview':preview,'token':token,'q':q,'filter_query':query.urlencode()})


@login_required
@require_POST
def seriousness(request,pk):
    require_analyst(request.user)
    get_object_or_404(visible_complaints(request.user),pk=pk)
    try: confirm_seriousness(request.user,pk,request.POST.get('value'),request.POST.get('reason',''),request.POST.get('hash'))
    except ValidationError as exc: messages.error(request,' / '.join(exc.messages))
    else: messages.success(request,'확인 이력을 저장했습니다. 기존 분석 근거는 유지됩니다. 정정본을 가져오려면 다시 미리보기 하세요. 승인 판단 자료가 바뀌면 재승인이 필요합니다.')
    return redirect('analysis-internal')


@login_required
@require_POST
def generate_pdf(request):
    require_analyst(request.user)
    form=AnalysisFilter(request.POST)
    if not form.is_valid():
        messages.error(request,'보고서 필터가 유효하지 않습니다.')
        return redirect('analysis')
    try: artifact=generate_analysis_report(request.user,form.cleaned_data)
    except ValidationError as exc:
        messages.error(request,' / '.join(exc.messages))
        return redirect('analysis')
    return redirect('analysis-artifact',artifact.pk)


@login_required
def artifact_download(request,pk):
    require_analyst(request.user)
    artifact=get_object_or_404(AnalysisArtifact,pk=pk)
    try: content=analysis_artifact_bytes(request.user,artifact)
    except ValidationError as exc:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest(' / '.join(exc.messages))
    response=HttpResponse(content,content_type='application/pdf')
    response['Content-Disposition']=f'attachment; filename="{artifact.report.number}-v{artifact.version}.pdf"'
    response['Cache-Control']='private, no-store'
    return response
