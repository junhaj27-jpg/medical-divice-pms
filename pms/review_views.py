import uuid
from django import forms
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, render, redirect
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import HttpResponse
import hashlib
from .models import MedicalDevice, PMSPeriodicReport, DuplicateReview
from .services import visible_complaints, role
from .workflow import privileged
from .periodic import create_periodic, finalize_periodic
from .duplicates import candidates, review_duplicate


class PeriodForm(forms.Form):
    request_key=forms.UUIDField(widget=forms.HiddenInput)
    device=forms.ModelChoiceField(label='제품',queryset=MedicalDevice.objects.all())
    start=forms.DateField(label='발생일 기준 시작',widget=forms.DateInput(attrs={'type':'date'}))
    end=forms.DateField(label='발생일 기준 종료',widget=forms.DateInput(attrs={'type':'date'}))
    is_example=forms.BooleanField(label='예시 데이터만',required=False)


@login_required
def periodic_pdf(request,pk):
    privileged(request.user)
    obj=get_object_or_404(PMSPeriodicReport,pk=pk,stage='FINAL')
    if not obj.pdf_content:
        return HttpResponse('이전 확정본에는 보존 PDF가 없습니다. 새 초안을 검토·확정하세요.',status=409)
    content=bytes(obj.pdf_content)
    if hashlib.sha256(content).hexdigest()!=obj.pdf_sha256:
        return HttpResponse('보존 PDF 무결성 오류입니다.',status=409)
    from .services import audit
    audit(request.user,'PMS_PERIOD_PDF',obj,after={'hash':obj.pdf_sha256})
    response=HttpResponse(content,content_type='application/pdf')
    response['Content-Disposition']=f'attachment; filename="pms-review-{pk}-v{obj.version}.pdf"'
    response['Cache-Control']='private, no-store'
    return response


class FinalForm(forms.Form):
    request_key=forms.UUIDField(widget=forms.HiddenInput)
    review_note=forms.CharField(label='검토 의견',widget=forms.Textarea,max_length=10000)
    confirm=forms.BooleanField(label='이 스냅샷을 내부 PMS 정기 검토 보고서로 확정합니다')


@login_required
def periodic_list(request):
    privileged(request.user)
    form=PeriodForm(request.POST if request.method=='POST' else None,initial={'request_key':uuid.uuid4()})
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data);data['device']=data['device'].pk
        try: obj=create_periodic(request.user,data)
        except ValidationError as exc: form.add_error(None,exc)
        else: return redirect('periodic-detail',pk=obj.pk)
    page=Paginator(PMSPeriodicReport.objects.defer('pdf_content').select_related('device','actor','reviewer').order_by('-pk'),20).get_page(request.GET.get('page'))
    return render(request,'pms/periodic_list.html',dict(form=form,items=page))


@login_required
def periodic_detail(request,pk):
    privileged(request.user)
    obj=get_object_or_404(PMSPeriodicReport,pk=pk)
    form=FinalForm(request.POST if request.method=='POST' else None,initial={'request_key':uuid.uuid4()})
    if request.method=='POST' and form.is_valid():
        try: result=finalize_periodic(request.user,pk,form.cleaned_data)
        except ValidationError as exc: form.add_error(None,exc)
        else: return redirect('periodic-detail',pk=result.pk)
    return render(request,'pms/periodic_detail.html',dict(item=obj,form=form))


@api_view(['GET','POST'])
def periodic_api(request,pk=None):
    privileged(request.user)
    if pk: get_object_or_404(PMSPeriodicReport,pk=pk)
    if request.method=='GET':
        qs=PMSPeriodicReport.objects.filter(pk=pk) if pk else PMSPeriodicReport.objects.order_by('-pk')
        page=Paginator(qs.order_by('-pk'),20).get_page(request.query_params.get('page'))
        fields=[f.name for f in PMSPeriodicReport._meta.fields if f.name != 'pdf_content']
        return Response(list(page.object_list.values(*fields)),headers={'X-Total-Count':str(page.paginator.count),'X-Page':str(page.number)})
    result=finalize_periodic(request.user,pk,dict(request.data)) if pk else create_periodic(request.user,dict(request.data))
    return Response({'id':result.pk,'version':result.version,'stage':result.stage})


class DuplicateForm(forms.Form):
    request_key=forms.UUIDField(widget=forms.HiddenInput)
    expected=forms.IntegerField(widget=forms.HiddenInput,min_value=0)
    other=forms.IntegerField(label='비교 사건 ID',min_value=1)
    verdict=forms.ChoiceField(label='판단',choices=[('DISTINCT','별개 사건'),('POSSIBLE','동일 사건 가능성'),('DEFER','판단 보류'),('EXCLUDE','관리자: 중복 확정·이 사건 집계 제외'),('INCLUDE','관리자: 집계 제외 해제')])
    reason=forms.CharField(label='판단 근거·변경 사유',widget=forms.Textarea,max_length=10000)
    confirm=forms.BooleanField(label='관리자 집계 제외 변경을 명시적으로 확인합니다',required=False)


@login_required
def duplicate_page(request,pk):
    case=get_object_or_404(visible_complaints(request.user),pk=pk)
    latest=case.duplicate_reviews.order_by('-pk').first()
    form=DuplicateForm(request.POST if request.method=='POST' else None,initial={'request_key':uuid.uuid4(),'expected':latest.pk if latest else 0})
    if request.method=='POST':
        privileged(request.user)
        if form.is_valid():
            try: review_duplicate(request.user,pk,form.cleaned_data)
            except ValidationError as exc: form.add_error(None,exc)
            else: return redirect('duplicate-review',pk=pk)
    history=case.duplicate_reviews.filter(other__in=visible_complaints(request.user)).select_related('actor').order_by('-pk')
    return render(request,'pms/duplicates.html',dict(item=case,candidates=candidates(request.user,case),history=history,form=form,can_review=role(request.user)!='STAFF'))


@api_view(['GET','POST'])
def duplicate_api(request,pk):
    case=get_object_or_404(visible_complaints(request.user),pk=pk)
    if request.method=='GET': return Response({'candidates':candidates(request.user,case),'history':list(case.duplicate_reviews.filter(other__in=visible_complaints(request.user)).order_by('-pk').values())})
    return Response({'id':review_duplicate(request.user,pk,dict(request.data)).pk})
