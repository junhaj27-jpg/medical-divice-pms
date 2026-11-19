import io,uuid
from functools import wraps
from django import forms
from django.core.exceptions import ValidationError,PermissionDenied
from django.http import Http404,JsonResponse,FileResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods,require_GET
from .market_views import market_view,device_for
from .market_service import product_markets
from .market_models import EU_COUNTRIES
from .models import MedicalDevice,Attachment
from .dental_models import DentalDraft
from .product_change_models import MRIProductChange,MRIChangeMarket
from . import product_changes as svc
from .dossier_views import input_data
from .review_task_views import TaskForm
from .file_security import safe_attachment_bytes,normalized_name

class RequestForm(forms.Form):
    kind=forms.ChoiceField(label='변경 유형',choices=[('SOFTWARE','소프트웨어 버전'),('LABEL','라벨')])
    before_value=forms.CharField(label='변경 전 값·버전',max_length=4000,widget=forms.Textarea(attrs={'rows':2}))
    after_value=forms.CharField(label='변경 후 값·버전',max_length=4000,widget=forms.Textarea(attrs={'rows':2}))
    reason=forms.CharField(label='변경 사유',max_length=4000,widget=forms.Textarea(attrs={'rows':2}))
    planned_on=forms.DateField(label='적용 예정일 (업무상 날짜)',widget=forms.DateInput(attrs={'type':'date'}))
    countries=forms.MultipleChoiceField(label='검토 요청 시장',widget=forms.CheckboxSelectMultiple)
    evidence_ids=forms.ModelMultipleChoiceField(label='관련 검사 통과 제품 증빙',queryset=Attachment.objects.none(),required=False)
    request_key=forms.UUIDField(widget=forms.HiddenInput)
    def __init__(self,*args,user,device,**kwargs):
        super().__init__(*args,**kwargs)
        countries=list(product_markets(user).filter(device=device,market__in=['US',*EU_COUNTRIES]).values_list('market',flat=True))
        self.fields['countries'].choices=[(c,'미국 (US)' if c=='US' else 'EU · '+c) for c in countries]
        scopes=set(countries)|({'EU'} if set(countries)&set(EU_COUNTRIES) else set())
        self.fields['evidence_ids'].queryset=Attachment.objects.filter(ra_profile__device=device,ra_profile__jurisdiction__in=scopes,scan_status='PASSED')

class DecisionForm(forms.Form):
    decisions=forms.MultipleChoiceField(label='시장별 RA 판단 (문서 개정과 시험 증빙 보완 동시 선택 가능)',choices=list(svc.DECISIONS.items()),widget=forms.CheckboxSelectMultiple)
    document_targets=forms.MultipleChoiceField(label='영향받는 문서 후보',required=False,widget=forms.CheckboxSelectMultiple)
    evidence_targets=forms.MultipleChoiceField(label='영향받는 시험·제품 증빙 후보',required=False,widget=forms.CheckboxSelectMultiple)
    rationale=forms.CharField(label='판단 사유·제출 필요 여부의 담당자 검토 근거',max_length=4000,widget=forms.Textarea)
    expected=forms.IntegerField(widget=forms.HiddenInput)
    def __init__(self,*args,user,review,**kwargs):
        super().__init__(*args,**kwargs)
        for field,category in [('document_targets','documents'),('evidence_targets','evidence')]:
            self.fields[field].choices=[(r['key'],r['title']+' · '+str(r['version'])) for r in svc.choices(user,review,category)]

class ActionTaskForm(TaskForm):
    action_type=forms.ChoiceField(label='후속 조치',choices=[('DOCUMENT','문서 개정'),('EVIDENCE','시험 증빙 보완')])
    target_key=forms.ChoiceField(label='당시 선택한 조치 대상')
    def __init__(self,*args,user,review,**kwargs):
        super().__init__(*args,user=user,creating=True,**kwargs)
        event=review.decisions.order_by('-pk').first();choices=[]
        if event:
            for category in ('documents','evidence'):
                for row in svc.choices(user,review,category):
                    if row['key'] in event.targets.get(category,[]):choices.append((row['key'],row['title']+' · '+str(row['version'])))
        self.fields['target_key'].choices=choices

def review_for(user,pk):
    review=get_object_or_404(MRIChangeMarket.objects.select_related('change__device','change__requested_by'),pk=pk)
    if not svc.can_review(user,review):raise Http404
    return review

def public_snapshot(user,review):
    snapshot=svc.deepcopy(review.snapshot)
    for category in ('documents','evidence','request_evidence'):
        snapshot[category]=[row if svc.candidate_access(user,review,row) else {'key':row['key'],'restricted':True,'title':'현재 권한으로 조회할 수 없는 자료'} for row in snapshot[category]]
    return snapshot

def form_data(request):return input_data(request) if request.content_type=='application/json' else request.POST

def valid_json(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if request.method=='POST' and request.content_type=='application/json':
            try:input_data(request)
            except ValidationError as exc:return JsonResponse({'error':str(exc)},status=400)
        return view(request,*args,**kwargs)
    return wrapped

@market_view
@never_cache
@require_http_methods(['GET','POST'])
@valid_json
def listing(request,pk=None,api=False):
    device=device_for(request,pk) if pk else None
    if device and device.product_type!='MRI':raise Http404
    error='';status=200
    data=form_data(request) if request.method=='POST' else None
    form=None
    if device:
        configuration=svc.configuration_payload(device)
        form=RequestForm(data,user=request.user,device=device,initial={'kind':'SOFTWARE','before_value':configuration.get('software_version','') if configuration else '', 'request_key':uuid.uuid4()})
    if request.method=='POST':
        if not device:raise Http404
        if form.is_valid():
            try:
                values=form.cleaned_data.copy();values['evidence_ids']=[f.pk for f in values['evidence_ids']]
                change,created=svc.submit(request.user,device,**values)
                if api:return JsonResponse({'change_id':change.pk,'created':created},status=201 if created else 200)
                return redirect('market-product-change',pk=change.pk)
            except (ValidationError,ValueError) as exc:error=str(exc);status=400
        else:status=400
    reviews=svc.visible_reviews(request.user)
    changes=MRIProductChange.objects.filter(pk__in={r.change_id for r in reviews}).select_related('device','requested_by').order_by('-pk')
    if device:changes=changes.filter(device=device)
    if api:return JsonResponse({'changes':[{'id':c.pk,'product_id':c.device_id,'kind':c.kind,'before':c.before_value,'after':c.after_value,'planned_on':str(c.planned_on)} for c in changes],'error':error,'errors':form.errors.get_json_data() if form else {}},status=status)
    products=MedicalDevice.objects.filter(product_type='MRI',pk__in=product_markets(request.user).values('device_id'))
    return render(request,'pms/markets/product_changes.html',{'device':device,'products':products,'changes':changes,'form':form,'error':error},status=status)

@market_view
@never_cache
@require_GET
def change_detail(request,pk,api=False):
    change=get_object_or_404(MRIProductChange.objects.select_related('device','requested_by'),pk=pk)
    reviews=svc.visible_reviews(request.user,change)
    if not reviews:raise Http404
    if api:return JsonResponse({'id':change.pk,'kind':change.kind,'before_value':change.before_value,'after_value':change.after_value,'reason':change.reason,'planned_on':str(change.planned_on),'requested_at':change.requested_at.isoformat(),'product_snapshot':change.product_snapshot,'reviews':[{'id':r.pk,'country':r.country,'status':r.status,'version':r.version} for r in reviews]})
    return render(request,'pms/markets/product_change.html',{'change':change,'reviews':reviews})

@market_view
@never_cache
@require_http_methods(['GET','POST'])
@valid_json
def market_review(request,pk,api=False):
    review=review_for(request.user,pk);event=review.decisions.order_by('-pk').first();error='';status=200
    form=DecisionForm(form_data(request) if request.method=='POST' else None,user=request.user,review=review,initial={'decisions':event.decisions if event else ['REVIEW'],'document_targets':event.targets['documents'] if event else [],'evidence_targets':event.targets['evidence'] if event else [],'rationale':event.rationale if event else '', 'expected':review.version})
    if request.method=='POST':
        if form.is_valid():
            try:
                values=form.cleaned_data
                svc.decide(request.user,review,expected=values['expected'],decisions=values['decisions'],targets={'documents':values['document_targets'],'evidence':values['evidence_targets']},rationale=values['rationale'],complete=request.POST.get('action')=='complete' if request.content_type!='application/json' else input_data(request).get('action')=='complete')
                if not api:return redirect('market-product-change-review',pk=pk)
                review=review_for(request.user,pk)
            except (ValidationError,ValueError,TypeError) as exc:error=str(exc);status=400
        else:status=400
    snapshot=public_snapshot(request.user,review)
    tasks=[]
    for action in review.actions.select_related('task_context__task'):
        if not svc.candidate_access(request.user,review,action.target_snapshot):continue
        context=getattr(action,'task_context',None)
        tasks.append({'action':action,'context':context,'task':context.task if context else None,'proof':context.task.review_evidence.select_related('actor') if context else []})
    history=review.decisions.select_related('actor').order_by('-pk')
    if api:return JsonResponse({'id':review.pk,'change_id':review.change_id,'country':review.country,'status':review.status,'version':review.version,'snapshot':snapshot,'history':[{'id':r.pk,'actor_id':r.actor_id,'at':r.created_at.isoformat(),'decisions':r.decisions,'targets':r.targets,'rationale':r.rationale,'complete':r.complete,'version':r.version} for r in history],
        'tasks':[{'action_id':row['action'].pk,'type':row['action'].action_type,'target_key':row['action'].target_key,'task_id':row['task'].pk if row['task'] else None,'status':row['task'].status if row['task'] else None,'proof':[{'id':p.pk,'snapshot':p.snapshot,'actor_id':p.actor_id,'at':p.created_at.isoformat()} for p in row['proof']]} for row in tasks],'error':error,'errors':form.errors.get_json_data()},status=status)
    return render(request,'pms/markets/product_change_review.html',{'review':review,'change':review.change,'snapshot':snapshot,'form':form,'history':history,'tasks':tasks,'error':error},status=status)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
@valid_json
def task_create(request,pk,api=False):
    review=review_for(request.user,pk);error='';status=200
    form=ActionTaskForm(form_data(request) if request.method=='POST' else None,user=request.user,review=review,initial={'action_type':'DOCUMENT','assignee':request.user.pk,'title':f'제품 변경 후속 검토 #{review.change_id} / {review.country}','criteria':'당시 변경값·대상 문서/시험 근거를 검토하고 개정·보완 결과를 증빙한다.','priority':'NORMAL','deadline_mode':'MANUAL'})
    if request.method=='POST':
        if form.is_valid():
            try:
                values=form.values();task_values={k:values[k] for k in ('assignee','title','criteria','priority','deadline_mode','due_at','basis_at','rule_id')}
                task,created=svc.create_task(request.user,review,action_type=values['action_type'],target_key=values['target_key'],**task_values)
                if api:return JsonResponse({'task_id':task.pk,'created':created},status=201 if created else 200)
                return redirect('market-review-task-detail',pk=task.pk)
            except (ValidationError,ValueError,TypeError) as exc:error=str(exc);status=400
        else:status=400
    if api:return JsonResponse({'error':error,'errors':form.errors.get_json_data()},status=status)
    return render(request,'pms/markets/product_change_task.html',{'review':review,'form':form,'error':error},status=status)

@market_view
@never_cache
@require_GET
def candidate(request,pk,key,download=False,api=False):
    review=review_for(request.user,pk)
    row=next((r for category in ('documents','evidence','request_evidence') for r in review.snapshot[category] if r['key']==key),None)
    if not row:raise Http404
    svc.require_candidate(request.user,review,row)
    if download:
        if not row.get('attachment_id'):raise Http404
        file=get_object_or_404(Attachment,pk=row['attachment_id']);data=safe_attachment_bytes(file)
        if file.sha256!=row['file_sha256']:raise Http404
        return FileResponse(io.BytesIO(data),as_attachment=True,filename=normalized_name(row['file_name']))
    snapshot=None
    if row.get('draft_id'):
        draft=get_object_or_404(DentalDraft,pk=row['draft_id'])
        if svc.review_tasks.digest(draft.snapshot)!=row['snapshot_hash']:raise Http404
        snapshot=draft.snapshot
    if api:return JsonResponse({'candidate':row,'draft_snapshot':snapshot})
    return render(request,'pms/markets/product_change_candidate.html',{'review':review,'row':row,'snapshot':snapshot})
