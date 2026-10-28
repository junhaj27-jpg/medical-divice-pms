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
    new_rule=forms.ModelChoiceField(label='새 규칙 버전 (초안은 검토 계산만 가능)',queryset=ReportingRule.objects.none())
    include_closed=forms.BooleanField(label='종료 사건 포함 (검토 전용)',required=False)
    inputs=forms.JSONField(label='사건별 확인 입력',required=False,help_text='{"사건번호": {"jurisdiction": "확인한 관할", "basis_at": "2026-10-28T10:00:00+09:00"}}. 생략하면 계산 불가 사유를 보존합니다.')
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        for key in ('old_rule','new_rule'): self.fields[key].queryset=rules_for(user)
    def clean_inputs(self):
        value=self.cleaned_data.get('inputs') or {}
        if not isinstance(value,dict) or any(not isinstance(v,dict) or set(v)-{'jurisdiction','basis_at'} or any(not isinstance(x,str) for x in v.values()) for v in value.values()):
            raise forms.ValidationError('사건번호별 관할·기준 일시 객체를 입력하세요.')
        return value


@login_required
def impact_list(request):
    privileged(request.user)
    form=AnalysisForm(request.POST if request.method=='POST' else None,user=request.user)
    if request.method=='POST' and form.is_valid():
        try:
            analysis=create_analysis(user=request.user,**form.cleaned_data)
            return redirect('impact-detail',analysis.pk)
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'pms/regulatory/impact_list.html',{'form':form,'items':analyses_for(request.user).order_by('-pk')})


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
