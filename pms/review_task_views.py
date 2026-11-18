import io
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404,JsonResponse,HttpResponse,FileResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from . import review_tasks as svc
from .models import WorkTask,Notification,Attachment
from .workflow import tasks_for
from .regulatory import rules_for
from .market_views import market_view
from .dossier_views import input_data
from .file_security import scan_attachment,safe_attachment_bytes,normalized_name
from .services import audit

class TaskForm(forms.Form):
    title=forms.CharField(label='업무 제목',max_length=200,required=False)
    assignee=forms.ModelChoiceField(label='담당자',queryset=get_user_model().objects.filter(is_active=True,profile__role__in=['RA_QA','ADMIN']),required=False)
    priority=forms.ChoiceField(label='우선순위',choices=[('', '변경 없음'),*WorkTask._meta.get_field('priority').choices],required=False)
    criteria=forms.CharField(label='완료 기준',max_length=4000,required=False,widget=forms.Textarea)
    deadline_mode=forms.ChoiceField(label='기한 방식',choices=[('','변경 없음'),('MANUAL','수동 지정 (업무 기한)'),('RULE','승인 규칙·등록 휴일로 계산 (업무 기한)')],required=False)
    due_at=forms.DateTimeField(label='수동 마감일',required=False,widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'))
    basis_at=forms.DateTimeField(label='규칙 계산 기준 일시',required=False,widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'))
    rule_id=forms.ModelChoiceField(label='계산 규칙 버전',queryset=None,required=False)
    reason=forms.CharField(label='변경·기한 조정 사유',max_length=2000,required=False,widget=forms.Textarea)
    comment=forms.CharField(label='검토 의견·완료 판단',max_length=4000,required=False,widget=forms.Textarea)
    evidence_ids=forms.ModelMultipleChoiceField(label='검사 통과 증빙 연결',queryset=Attachment.objects.none(),required=False)
    criteria_confirmed=forms.BooleanField(label='완료 기준과 이번 회차 증빙을 확인함',required=False)
    def __init__(self,*args,user,task=None,creating=False,**kwargs):
        super().__init__(*args,**kwargs);self.fields['rule_id'].queryset=rules_for(user).filter(state__in=['APPROVED','EFFECTIVE'])
        if task:self.fields['evidence_ids'].queryset=svc.files_for(task)
        if creating:
            for key in ('title','assignee','criteria','deadline_mode'):self.fields[key].required=True
    def values(self):
        data=self.cleaned_data.copy()
        data['title']=data.get('title') or None
        data['priority']=data.get('priority') or None
        for key in ('due_at','basis_at'):
            if data.get(key):data[key]=data[key].isoformat()
        if data.get('rule_id'):data['rule_id']=data['rule_id'].pk
        data['evidence_ids']=[r.pk for r in data.get('evidence_ids',[])]
        return data

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def create(request,kind,pk,api=False):
    error='';status=200
    try:
        data=input_data(request) if request.method=='POST' else request.GET
        if request.method=='GET' and not data.get('country') and kind in ('CAPA','ADOPTION_IMPACT'):
            from .market_service import case_markets,product_markets
            if kind=='CAPA':
                evaluation=get_object_or_404(svc.CAPAEvaluation,pk=pk)
                countries=list(case_markets(request.user).filter(complaint_id=evaluation.capa.complaint_id).values_list('market',flat=True))
            else:
                adoption=get_object_or_404(svc.SearchEvidenceAdoption,pk=pk)
                if not svc.adoption_access(request.user,adoption):raise Http404
                if adoption.draft_id:
                    market=adoption.draft.project.market
                    countries=list(product_markets(request.user).filter(device_id=adoption.draft.project.device_id,market__in=['US'] if market=='US' else ['DE','FR','ES','IT']).values_list('market',flat=True))
                else:countries=[adoption.review.result.run.market]
            return render(request,'pms/review_task_country.html',{'countries':countries,'section':data.get('section',''),'source_fingerprint':data.get('source_fingerprint','')})
        origin=svc.source(request.user,kind,pk,data.get('country',''),data.get('section',''),data.get('source_fingerprint',''))
    except (ValueError,ValidationError) as exc:
        if api:return JsonResponse({'error':str(exc)},status=400)
        raise Http404
    except (svc.RADocumentReview.DoesNotExist,svc.RADocumentRevision.DoesNotExist,svc.SearchEvidenceAdoption.DoesNotExist,svc.CAPAEvaluation.DoesNotExist):raise Http404
    form=TaskForm(data if request.method=='POST' else None,user=request.user,creating=True,initial={'title':origin['title'][:200],'assignee':request.user.pk,'priority':'NORMAL','deadline_mode':'MANUAL','criteria':'연결된 문서·조항을 검토하고 판단 사유와 증빙을 기록한다.'})
    if request.method=='POST' and form.is_valid():
        try:
            values=form.values()
            values={k:values[k] for k in ('title','assignee','criteria','priority','deadline_mode','due_at','basis_at','rule_id')}
            task,created=svc.create(request.user,kind,pk,**values,country=data.get('country',''),section=data.get('section',''),source_fingerprint=data.get('source_fingerprint',''))
            if api:return JsonResponse({'task_id':task.pk,'created':created},status=201 if created else 200)
            return redirect('market-review-task-detail',pk=task.pk)
        except ValidationError as exc:error=str(exc);status=400
    elif request.method=='POST':status=400
    if api:return JsonResponse({'error':error,'errors':form.errors.get_json_data()},status=status)
    return render(request,'pms/review_task_new.html',{'form':form,'origin':origin,'error':error,'country':data.get('country',''),'section':data.get('section',''),'source_fingerprint':data.get('source_fingerprint','')},status=status)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def detail(request,pk,api=False,download=None):
    task=get_object_or_404(tasks_for(request.user),pk=pk)
    if not hasattr(task,'review_context'):raise Http404
    context=task.review_context;error='';status=200
    if download:
        row=get_object_or_404(task.review_evidence,pk=download)
        data=safe_attachment_bytes(row.attachment)
        if row.snapshot['sha256']!=row.attachment.sha256:raise Http404
        return FileResponse(io.BytesIO(data),as_attachment=True,filename=normalized_name(row.snapshot['name']))
    data=None
    if request.method=='POST':
        try:data=input_data(request)
        except ValidationError as exc:error=str(exc);status=400
    form=TaskForm(data,user=request.user,task=task,initial={'assignee':task.assignee_id,'title':task.title,'priority':task.priority,'criteria':context.criteria})
    if request.method=='POST' and data and data.get('action')=='upload':
        file=request.FILES.get('file')
        if not file:error='증빙 파일을 선택하세요.';status=400
        else:
            attachment=Attachment(complaint_id=task.complaint_id,ra_profile_id=task.ra_profile_id,file=file,original_name=normalized_name(file.name),uploaded_by=request.user)
            try:
                attachment.full_clean();attachment.save();scan_attachment(attachment,request.user)
                if api:return JsonResponse({'attachment_id':attachment.pk,'scan_status':attachment.scan_status},status=201)
                return redirect('market-review-task-detail',pk=task.pk)
            except ValidationError as exc:error=str(exc);status=400
    elif request.method=='POST' and data and form.is_valid():
        try:
            values=form.values()
            task=svc.update(request.user,task,expected=data.get('expected',0),action=data.get('action',''),**values)
            if not api:return redirect('market-review-task-detail',pk=task.pk)
            context=task.review_context
        except (ValidationError,ValueError,TypeError) as exc:error=str(exc);status=400
    elif request.method=='POST' and not error:status=400
    history=list(task.history.select_related('actor').order_by('-pk'))
    if api:return JsonResponse({'id':task.pk,'title':task.title,'assignee_id':task.assignee_id,'due_at':task.due_at.isoformat(),'status':task.status,'priority':task.priority,'version':context.version,'cycle':context.cycle,'criteria':context.criteria,'deadline':context.deadline_snapshot,'source':context.source_snapshot,'completed_by':context.completed_by_id,'completed_at':context.completed_at.isoformat() if context.completed_at else None,'history':[{'id':r.pk,'actor_id':r.actor_id,'at':r.created_at.isoformat(),'before':r.before,'after':r.after} for r in history],'error':error,'errors':form.errors.get_json_data()},status=status)
    return render(request,'pms/review_task_detail.html',{'task':task,'context':context,'form':form,'history':history,'evidence':task.review_evidence.select_related('attachment','actor'),'error':error},status=status)

def notifications_for(user):
    return Notification.objects.filter(user=user).filter(Q(work_task__isnull=True)|Q(work_task__in=tasks_for(user).order_by()))

@login_required
@never_cache
@require_http_methods(['GET','POST'])
def notifications(request,api=False,pk=None):
    if pk is not None:
        item=get_object_or_404(notifications_for(request.user),pk=pk)
        if request.method!='POST':return HttpResponse(status=405)
        if not item.read_at:item.read_at=timezone.now();item.save(update_fields=['read_at'])
        if api:return JsonResponse({'id':item.pk,'read_at':item.read_at.isoformat()})
        return redirect('market-notifications')
    if request.method!='GET':return HttpResponse(status=405)
    items=notifications_for(request.user).order_by('-pk')
    if api:return JsonResponse({'items':[{'id':n.pk,'title':n.title,'task_id':n.work_task_id,'read_at':n.read_at.isoformat() if n.read_at else None,'due_at':n.due_at.isoformat() if n.due_at else None} for n in items[:200]]})
    return render(request,'pms/notifications.html',{'items':items[:200]})
