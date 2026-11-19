from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe
from django.views.decorators.cache import never_cache
from .market_views import market_view
from .period_models import PMSPeriodAction
from . import period_analysis as svc
from .review_task_views import TaskForm
from .dossier_views import input_data

class SnapshotFilter(forms.Form):
    device=forms.ModelChoiceField(label='제품',queryset=None,required=False)
    market=forms.ChoiceField(label='시장',required=False)
    saved_from=forms.DateField(label='저장일 시작 (Asia/Seoul)',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    saved_to=forms.DateField(label='저장일 종료 (Asia/Seoul)',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs);base=svc.PeriodForm(user=user)
        self.fields['device'].queryset=base.fields['device'].queryset
        self.fields['market'].choices=[('','전체'),*base.fields['market'].choices]
    def clean(self):
        data=super().clean()
        if data.get('saved_from') and data.get('saved_to') and data['saved_from']>data['saved_to']:raise forms.ValidationError('저장일 범위를 확인하세요.')
        return data

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def compare(request,api=False):
    error='';criteria=None;result=None;token='';status=200
    try:data=input_data(request) if request.method=='POST' else request.GET
    except ValidationError as exc:return JsonResponse({'error':'; '.join(exc.messages)},status=400)
    if request.method=='POST' and data.get('action')=='save':
        try:
            snapshot=svc.save_preview(request.user,data.get('token',''))
            if api:return JsonResponse({'id':snapshot.pk},status=201)
            return redirect('market-pms-snapshot',pk=snapshot.pk)
        except ValidationError as exc:error='; '.join(exc.messages);status=400
    today=timezone.localdate();defaults={'basis':'reported_on','a_start':today-timedelta(days=59),'a_end':today-timedelta(days=30),'b_start':today-timedelta(days=29),'b_end':today,'example':'real','display_timezone':'Asia/Seoul'}
    form=svc.PeriodForm(data or None,user=request.user,initial=defaults)
    if not error and data and form.is_valid():
        criteria,result=svc.compare(request.user,form.cleaned_data);token=svc.preview_token(request.user,criteria,result)
    elif data and not error:status=400
    generated_display=datetime.fromisoformat(result['generated_at']).astimezone(ZoneInfo(criteria['display_timezone'])).isoformat() if result else ''
    if api:return JsonResponse({'criteria':criteria,'result':result,'token':token,'error':error,'errors':form.errors.get_json_data()},status=status)
    return render(request,'pms/period_compare.html',locals(),status=status)

@market_view
@never_cache
@require_safe
def listing(request,api=False):
    form=SnapshotFilter(request.GET or None,user=request.user);qs=svc.snapshots_for(request.user)
    if form.is_bound:
        if form.is_valid():
            d=form.cleaned_data
            if d.get('device'):qs=qs.filter(device=d['device'])
            if d.get('market'):qs=qs.filter(market=d['market'])
            if d.get('saved_from'):qs=qs.filter(created_at__date__gte=d['saved_from'])
            if d.get('saved_to'):qs=qs.filter(created_at__date__lte=d['saved_to'])
        else:qs=qs.none()
    page=Paginator(qs,30).get_page(request.GET.get('page'))
    if api:return JsonResponse({'items':[{'id':s.pk,'market':s.market,'criteria':s.criteria,'saved_at':s.created_at.isoformat()} for s in page],'pages':page.paginator.num_pages},status=400 if form.errors else 200)
    return render(request,'pms/period_list.html',locals(),status=400 if form.errors else 200)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def detail(request,pk,api=False,output=''):
    snapshot=get_object_or_404(svc.snapshots_for(request.user),pk=pk)
    if output:
        if request.method!='GET':return HttpResponse(status=405)
        response=HttpResponse(svc.export_csv(snapshot),content_type='text/csv; charset=utf-8')
        response['Content-Disposition']=f'attachment; filename="pms-period-{snapshot.pk}.csv"'
        return response
    error='';status=200
    if request.method=='POST':
        try:
            data=input_data(request)
            if data.get('action')!='comment':raise ValidationError('허용되지 않은 동작입니다.')
            svc.comment(request.user,snapshot,data.get('note',''))
            if not api:return redirect('market-pms-snapshot',pk=pk)
        except ValidationError as exc:error='; '.join(exc.messages);status=400
    criteria=snapshot.criteria;result=snapshot.result
    generated_display=datetime.fromisoformat(result['generated_at']).astimezone(ZoneInfo(criteria['display_timezone'])).isoformat()
    saved_display=snapshot.created_at.astimezone(ZoneInfo(criteria['display_timezone'])).isoformat()
    comments=list(snapshot.comments.select_related('actor'));actions=list(snapshot.actions.select_related('task_context__task'))
    if api:return JsonResponse({'id':snapshot.pk,'criteria':criteria,'result':result,'actor':snapshot.actor_id,'saved_at':snapshot.created_at.isoformat(),'comments':[{'id':c.pk,'actor':c.actor_id,'note':c.note,'at':c.created_at.isoformat()} for c in comments],'tasks':[{'kind':a.kind,'id':a.task_context.task_id,'status':a.task_context.task.status} for a in actions if hasattr(a,'task_context')],'error':error},status=status)
    return render(request,'pms/period_detail.html',locals(),status=status)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def task_create(request,pk,kind,api=False):
    snapshot=get_object_or_404(svc.snapshots_for(request.user),pk=pk)
    if kind not in dict(PMSPeriodAction.KINDS):return HttpResponse(status=404)
    existing=snapshot.actions.filter(kind=kind,task_context__isnull=False).select_related('task_context').first()
    if existing:
        if api:return JsonResponse({'task_id':existing.task_context.task_id,'created':False})
        return redirect('market-review-task-detail',pk=existing.task_context.task_id)
    try:data=input_data(request) if request.method=='POST' else None
    except ValidationError as exc:return JsonResponse({'error':'; '.join(exc.messages)},status=400)
    form=TaskForm(data,user=request.user,creating=True,initial={'title':f'PMS {dict(PMSPeriodAction.KINDS)[kind]} #{pk}','assignee':request.user.pk,'priority':'NORMAL','deadline_mode':'MANUAL','criteria':'집계 기준과 추이를 확인하고 추가 조사 또는 CAPA 검토 결과·증빙을 기록한다.'})
    error='';status=200
    if request.method=='POST':
        status=400
        if form.is_valid():
            try:
                values=form.values();values={k:values[k] for k in ('title','assignee','criteria','priority','deadline_mode','due_at','basis_at','rule_id')}
                task,created=svc.create_task(request.user,snapshot,kind,**values)
                if api:return JsonResponse({'task_id':task.pk,'created':created},status=201 if created else 200)
                return redirect('market-review-task-detail',pk=task.pk)
            except ValidationError as exc:error='; '.join(exc.messages)
    if api:return JsonResponse({'error':error,'errors':form.errors.get_json_data()},status=status)
    return render(request,'pms/period_task.html',locals(),status=status)
