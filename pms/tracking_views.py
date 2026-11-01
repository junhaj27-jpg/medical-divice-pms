import uuid
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import RegulatoryReport, SubmissionVersion
from .safety import signals_for
from .signal_tracking import track_signal
from .submissions import prepare_submission, record_submission, save_submission_plan
from .services import visible_complaints, role
from .workflow import privileged


class TrackingForm(forms.Form):
    request_key=forms.UUIDField(widget=forms.HiddenInput)
    note=forms.CharField(label='확인 내용·결과·사유',widget=forms.Textarea,required=False,max_length=10000)


def form_for(mode, data=None):
    form=TrackingForm(data,initial={'request_key':uuid.uuid4()})
    def add(name,field): form.fields[name]=field
    if mode=='signal':
        add('kind',forms.ChoiceField(label='작업',choices=[('INVESTIGATE','조사 기록'),('NO_ACTION','조치 불필요 판단'),('LINK','기존 조치 연결'),('DRAFT_CAPA','신규 CAPA 초안 명시적 요청'),('DRAFT_RECALL','신규 리콜 초안 명시적 요청'),('EFFECT','효과 확인'),('CLOSE','종결'),('REOPEN','재검토')]))
        for name,label in [('assignee','담당자 ID'),('complaint','신호 근거 사건 ID'),('capa','기존 CAPA ID'),('recall','기존 리콜 ID'),('evaluation','기존 CAPA 효과성 평가 ID')]: add(name,forms.IntegerField(label=label,required=False,min_value=1))
        add('basis',forms.CharField(label='조사 근거',required=False,widget=forms.Textarea,max_length=10000))
        for name,label in [('due_on','조사·조치 기한'),('evaluated_on','효과 확인일')]: add(name,forms.DateField(label=label,required=False,widget=forms.DateInput(attrs={'type':'date'})))
        add('verdict',forms.ChoiceField(label='리콜 효과 판정',required=False,choices=[('','선택'),('PASS','적합'),('FAIL','미흡·재검토')]))
    elif mode=='prepare':
        add('report_kind',forms.ChoiceField(label='보고 구분',choices=SubmissionVersion._meta.get_field('report_kind').choices))
        add('artifact',forms.IntegerField(label='현재 승인 내용의 PDF ID',min_value=1))

    else:
        add('state',forms.ChoiceField(label='기록 상태',choices=[('SUBMITTED','제출 완료 확인'),('ACKNOWLEDGED','접수 확인'),('SUPPLEMENT_REQUESTED','보완 요청'),('SUPPLEMENT_SUBMITTED','보완 제출 완료 확인'),('COMPLETED','처리 완료')]))
        add('submitted_at',forms.DateTimeField(label='실제 제출 일시 (시간대 포함)',required=False))
        add('submitter',forms.CharField(label='실제 제출자',max_length=200,required=False))
        add('receipt_number',forms.CharField(label='접수번호',max_length=200,required=False))
        add('replacement',forms.IntegerField(label='보완 제출용 새 제출본 ID',required=False,min_value=1))
        add('due_at',forms.DateTimeField(label='수동 후속 기한',required=False))
        add('due_reason',forms.CharField(label='수동 기한 설정 사유',required=False,max_length=2000))
    add('evidence',forms.CharField(label='검사 통과 증빙 ID (쉼표 구분)',required=False))
    add('confirm',forms.BooleanField(label='신규 초안 생성 또는 실제 제출 완료를 명시적으로 요청·확인합니다',required=False))
    return form


def cleaned(form):
    data={k:(v.isoformat() if hasattr(v,'isoformat') else str(v) if isinstance(v,uuid.UUID) else v) for k,v in form.cleaned_data.items() if v is not None and v!=''}
    try: data['evidence']=[int(v.strip()) for v in data.get('evidence','').split(',') if v.strip()]
    except ValueError: raise ValidationError('증빙 ID는 숫자로 입력하세요.') from None
    return data


@login_required
def tracking_page(request, mode, pk):
    privileged(request.user)
    if mode=='signal':
        obj=get_object_or_404(signals_for(request.user),pk=pk); records=obj.tracking.order_by('pk')
        service=track_signal; title=f'안전 신호 #{pk} 조사·조치 추적'
    elif mode=='prepare':
        obj=get_object_or_404(RegulatoryReport,pk=pk,complaint__in=visible_complaints(request.user));records=obj.submissions.order_by('version')
        service=prepare_submission;title=f'규제보고 #{pk} 제출 준비'
    else:
        obj=get_object_or_404(SubmissionVersion,pk=pk,report__complaint__in=visible_complaints(request.user));records=obj.events.order_by('pk')
        service=record_submission;title=f'제출본 #{pk} v{obj.version} 이력'
    plan_form=None
    if mode=='prepare':
        class PlanForm(forms.Form):
            submission_authority=forms.CharField(label='승인 대상: 제출 기관',max_length=200)
            submission_channel=forms.CharField(label='승인 대상: 제출 경로',max_length=200)
        plan_form=PlanForm(request.POST if request.POST.get('operation')=='plan' else None,initial={'submission_authority':obj.submission_authority,'submission_channel':obj.submission_channel})
        if request.method=='POST' and request.POST.get('operation')=='plan' and plan_form.is_valid():
            try: save_submission_plan(request.user,pk,plan_form.cleaned_data)
            except ValidationError as exc: plan_form.add_error(None,exc)
            else: return redirect(request.path)
    form=form_for(mode,request.POST if request.method=='POST' and request.POST.get('operation')!='plan' else None)
    if request.method=='POST' and form.is_valid():
        try: result=service(request.user,pk,cleaned(form))
        except ValidationError as exc: form.add_error(None,exc)
        else:
            if mode=='prepare': return redirect('submission-tracking',pk=result.pk)
            return redirect(request.path)
    return render(request,'pms/tracking.html',dict(title=title,item=obj,records=records,form=form,mode=mode,plan_form=plan_form))


@api_view(['GET','POST'])
def tracking_api(request, mode, pk):
    privileged(request.user)
    if mode=='signal':
        obj=get_object_or_404(signals_for(request.user),pk=pk);qs=obj.tracking.all();service=track_signal
    elif mode=='prepare':
        obj=get_object_or_404(RegulatoryReport,pk=pk,complaint__in=visible_complaints(request.user));qs=obj.submissions.all();service=prepare_submission
    else:
        obj=get_object_or_404(SubmissionVersion,pk=pk,report__complaint__in=visible_complaints(request.user));qs=obj.events.all();service=record_submission
    if request.method=='GET': return Response(list(qs.order_by('pk').values()))
    if mode=='prepare' and request.data.get('operation')=='plan': return Response({'id':save_submission_plan(request.user,pk,dict(request.data)).pk})
    result=service(request.user,pk,dict(request.data))
    return Response({'id':result.pk},status=200)
