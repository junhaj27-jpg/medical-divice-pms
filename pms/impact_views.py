from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from .models import ReportingRule, ImpactReview
from .regulatory import rules_for, DISPLAY_LABELS
from .workflow import privileged
from .impact import analyses_for, create_analysis, stale_reason, process_review


class AnalysisForm(forms.Form):
    old_rule=forms.ModelChoiceField(label='기존 규칙 버전',queryset=ReportingRule.objects.none())
    new_rule=forms.ModelChoiceField(label='새 규칙 버전',queryset=ReportingRule.objects.none())
    include_closed=forms.BooleanField(label='종료 사건 포함 (검토 전용)',required=False)
    token=forms.CharField(widget=forms.HiddenInput)
    bulk_confirm=forms.BooleanField(label='선택한 사건에만 공통 값을 적용함을 확인',required=False)
    bulk_jurisdiction=forms.CharField(label='공통 관할',required=False,max_length=100)
    bulk_basis_at=forms.CharField(label='공통 기준 일시 (UTC 오프셋 포함)',required=False,max_length=80)
    bulk_reason=forms.CharField(label='공통 확인 사유',required=False,max_length=2000)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        for key in ('old_rule','new_rule'): self.fields[key].queryset=rules_for(user)


class CaseInput(forms.Form):
    case_id=forms.IntegerField(widget=forms.HiddenInput)
    selected=forms.BooleanField(label='선택',required=False)
    jurisdiction=forms.CharField(label='확인한 관할',required=False,max_length=100)
    basis_at=forms.CharField(label='기준 일시 (예: 2026-10-28T10:00:00+09:00)',required=False,max_length=80)
    reason=forms.CharField(label='확인 사유',required=False,max_length=2000)


@login_required
def impact_list(request):
    import uuid
    from datetime import datetime, timezone as dt_timezone
    from django.core import signing
    from django.core.paginator import Paginator
    from django.db.models import Q
    from django.utils import timezone
    from .services import visible_complaints
    from .impact import candidate_preview
    cases=visible_complaints(request.user).select_related('device').order_by('pk')
    privileged(request.user)
    q=request.GET.get('q','').strip()
    if q:
        query=Q(title__icontains=q)|Q(device__name__icontains=q)
        if q.removeprefix('CMP-').isdigit(): query|=Q(pk=int(q.removeprefix('CMP-')))
        cases=cases.filter(query)
    if request.GET.get('status'): cases=cases.filter(status=request.GET['status'])
    if request.GET.get('example') in ('0','1'): cases=cases.filter(is_example=request.GET['example']=='1')
    page=Paginator(cases,20).get_page(request.GET.get('page'))
    allowed=[c.pk for c in page]
    initial_token=signing.dumps({'ids':allowed,'key':str(uuid.uuid4()),'user':request.user.pk},salt='impact-rows')
    form=AnalysisForm(request.POST if request.method=='POST' else None,user=request.user,initial={'token':initial_token})
    RowSet=forms.formset_factory(CaseInput,extra=0,max_num=20,validate_max=True,absolute_max=20)
    rows=RowSet(request.POST if request.method=='POST' else None,initial=[{'case_id':c.pk} for c in page],prefix='rows')
    valid=form.is_valid() and rows.is_valid() if request.method=='POST' else False
    if valid:
        try:
            scope=signing.loads(form.cleaned_data['token'],salt='impact-rows',max_age=7200)
            if scope['user']!=request.user.pk or scope['ids']!=allowed: raise ValidationError('사건 목록이 변경되었습니다. 다시 조회하세요.')
            ids=[r.cleaned_data['case_id'] for r in rows]
            if ids!=allowed:
                for i,row in enumerate(rows):
                    if i>=len(allowed) or row.cleaned_data['case_id']!=allowed[i]: row.add_error('selected','허용되지 않은 사건 또는 중복 행입니다.')
                raise ValidationError('허용되지 않은 사건 또는 중복 행입니다.')
            inputs={}; selected=[]
            bulk=any(form.cleaned_data[k] for k in ('bulk_jurisdiction','bulk_basis_at','bulk_reason'))
            if bulk and not form.cleaned_data['bulk_confirm']: raise ValidationError('공통 값 적용은 대상 선택과 명시적 확인이 필요합니다.')
            for row,case in zip(rows,page):
                d=row.cleaned_data
                if not d['selected']: continue
                selected.append(case.pk)
                value={k:form.cleaned_data['bulk_'+k] if bulk else d[k] for k in ('jurisdiction','basis_at','reason')}
                for k in value:
                    if not value[k]: row.add_error(k,'선택한 사건의 필수 확인 입력입니다.')
                if value['basis_at']:
                    try:
                        dt=datetime.fromisoformat(value['basis_at'])
                        if dt.tzinfo is None or dt.utcoffset() is None: raise ValueError()
                        value['basis_at']=dt.astimezone(dt_timezone.utc).isoformat()
                    except ValueError: row.add_error('basis_at','유효한 일시와 UTC 오프셋을 입력하세요. 예: +09:00')
                if case.status=='CLOSED' and not form.cleaned_data['include_closed']: row.add_error('selected','종료 사건 포함을 확인하세요.')
                if not case.rule_applications.filter(rule=form.cleaned_data['old_rule']).exists():
                    from .regulatory import matches_case
                    if case.status=='CLOSED' or not matches_case(form.cleaned_data['new_rule'],case): row.add_error('selected','선택 규칙의 후보 사건이 아닙니다.')
                error=candidate_preview(form.cleaned_data['new_rule'],case,value)['error']
                if error: row.add_error(None,error)
                inputs[str(case.pk)]=value
            if not selected: raise ValidationError('분석할 사건을 선택하세요.')
            if not any(r.errors for r in rows):
                analysis=create_analysis(user=request.user,old_rule=form.cleaned_data['old_rule'],new_rule=form.cleaned_data['new_rule'],include_closed=form.cleaned_data['include_closed'],inputs=inputs,case_ids=selected,submission_key=scope['key'])
                return redirect('impact-detail',analysis.pk)
        except (signing.BadSignature,KeyError,ValidationError) as exc:
            form.add_error(None,exc if isinstance(exc,ValidationError) else '입력 유효시간이 지났거나 사건 목록이 유효하지 않습니다.')
    rendered=[]
    for case,row in zip(page,rows):
        previous=case.rule_applications.select_related('rule').order_by('-pk').first()
        rendered.append((case,row,previous))
    query=request.GET.copy();query.pop('page',None)
    return render(request,'pms/regulatory/impact_list.html',{'form':form,'formset':rows,'rows':rendered,'page':page,'filter_query':query.urlencode(),'q':q,'statuses':case_statuses(),'user_timezone':timezone.get_current_timezone_name(),'items':analyses_for(request.user).order_by('-pk')[:50]})


def case_statuses():
    from .models import CustomerComplaint
    return CustomerComplaint.Status.choices


@login_required
def impact_detail(request,pk):
    privileged(request.user)
    analysis=get_object_or_404(analyses_for(request.user),pk=pk)
    reviews=analysis.reviews.select_related('complaint','task__assignee')
    if request.GET.get('status'): reviews=reviews.filter(status=request.GET['status'])
    if request.GET.get('assignee','').isdigit(): reviews=reviews.filter(task__assignee_id=request.GET['assignee'])
    if request.GET.get('shortened') in ('0','1'): reviews=reviews.filter(shortened=request.GET['shortened']=='1')
    rows=[(review,stale_reason(review,request.user)) for review in reviews]
    changes=[(DISPLAY_LABELS.get(k,k),v['old'],v['new']) for k,v in analysis.snapshot['changes'].items()]
    return render(request,'pms/regulatory/impact_detail.html',{'item':analysis,'rows':rows,'changes':changes,'statuses':ImpactReview._meta.get_field('status').choices,'users':User.objects.filter(is_active=True)})


@login_required
@require_POST
def impact_process(request,pk):
    privileged(request.user)
    review=get_object_or_404(ImpactReview,pk=pk,analysis__in=analyses_for(request.user))
    assignee=get_object_or_404(User,pk=request.POST['assignee'],is_active=True) if request.POST.get('assignee','').isdigit() else None
    try: process_review(review,request.user,request.POST.get('status'),request.POST.get('reason',''),assignee)
    except ValidationError as exc: messages.error(request,' / '.join(exc.messages))
    return redirect('impact-detail',review.analysis_id)
