import csv,io,json,difflib
from django import forms
from django.core.exceptions import ValidationError,PermissionDenied
from django.http import Http404,HttpResponse,JsonResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.db import transaction
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .market_views import market_view
from .market_service import allowed_markets,product_markets
from .market_models import EU_COUNTRIES
from .models import MedicalDevice
from .dental_models import DentalProject,WritingTemplate
from .dental_views import guide_for
from .dossier_models import RADocument,RADocumentRevision,RASourceImpactReview
from . import dossier as svc
from .search_models import SearchEvidenceAdoption
from .search_history import adoption_access
from .source_search import candidates
from .services import audit

class CreateForm(forms.Form):
    device=forms.ModelChoiceField(label='등록 의료기기',queryset=MedicalDevice.objects.none())
    template=forms.ModelChoiceField(label='기존 문서 템플릿',queryset=WritingTemplate.objects.filter(state='PUBLISHED'))
    document_type=forms.ChoiceField(label='문서 유형',choices=list(svc.TYPES.items()))
    country=forms.ChoiceField(label='대상 국가')
    language=forms.ChoiceField(label='작성 언어',choices=[('en','English'),('ko-KR','한국어')])
    reason=forms.CharField(label='작성 사유',max_length=2000)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs);self.user=user
        self.fields['device'].queryset=MedicalDevice.objects.filter(pk__in=product_markets(user).values('device_id'))
        self.fields['country'].choices=[(c,c) for c in allowed_markets(user) if c in ('US',*EU_COUNTRIES)]
    def clean(self):
        data=super().clean();template=data.get('template');device=data.get('device');country=data.get('country')
        if template and country:
            market='US' if country=='US' else 'EU'
            if template.market!=market:raise ValidationError('선택한 국가와 템플릿 시장이 다릅니다.')
            existing=DentalProject.objects.filter(device=device,market=market).first()
            if existing and existing.template_id!=template.pk:raise ValidationError('기존 프로젝트의 템플릿을 선택하세요. 템플릿 전환은 기존 작성 화면에서 처리합니다.')
            if not product_markets(self.user).filter(device=device,market=country).exists() or not svc.writing_access(self.user,device,market):raise ValidationError('이 제품 시장에 접근할 수 없습니다.')
        return data

    def bind_user(self,user):self.user=user;return self

def csv_cell(value):
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value

def input_data(request):
    if request.content_type=='application/json':
        try:
            data=json.loads(request.body)
            if not isinstance(data,dict):raise ValueError()
            return data
        except (ValueError,UnicodeError):raise ValidationError('JSON 객체를 입력하세요.')
    data=request.POST.dict()
    for key in request.POST:
        if key.startswith('refs_'):data[key]=request.POST.getlist(key)
    return data

def revision_for(user,pk):
    revision=get_object_or_404(RADocumentRevision.objects.select_related('document__project__device','document__project__template','document__project__guide','draft'),pk=pk)
    if not svc.revision_access(user,revision):raise Http404
    return revision

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def listing(request,api=False):
    error='';status=200
    try:data=input_data(request) if request.method=='POST' else None
    except ValidationError as exc:data={};error=str(exc);status=400
    form=CreateForm(data,user=request.user).bind_user(request.user)
    if request.method=='POST' and not error and form.is_valid():
        try:
            values=form.cleaned_data.copy();device=values.pop('device');template=values.pop('template');market=template.market
            with transaction.atomic():
                # Product lock serializes project creation with existing writing operations.
                MedicalDevice.objects.select_for_update().get(pk=device.pk)
                project,_=DentalProject.objects.get_or_create(device=device,market=market,defaults={'owner':request.user,'guide':guide_for(),'template':template,'specification':{
                    'product_name':device.name,'model':device.model_number,'intended_use':'','example':device.model_number.startswith('DEMO-'),'changed':False}})
                revision=svc.create_document(request.user,project,values.pop('document_type'),**values)
            if api:return JsonResponse({'revision_id':revision.pk,'document_id':revision.document_id},status=201)
            return redirect('market-ra-document',pk=revision.pk)
        except ValidationError as exc:error=str(exc);status=400
    elif request.method=='POST':status=400
    documents=list(svc.visible_documents(request.user).order_by('-pk')[:100])
    if api:return JsonResponse({'documents':[{'id':d.pk,'device_id':d.project.device_id,'type':d.document_type,'country':d.country,'language':d.language} for d in documents],'errors':form.errors.get_json_data(),'error':error},status=status)
    for doc in documents:doc.latest=doc.revisions.order_by('-number').first()
    return render(request,'pms/markets/ra_document_list.html',{'form':form,'documents':documents,'error':error},status=status)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def detail(request,pk,api=False,output=None):
    revision=revision_for(request.user,pk);error='';status=200
    if output:
        if request.method!='GET':return HttpResponse(status=405)
        if output=='docx':
            payload=svc.export_docx(request.user,revision);response=HttpResponse(payload,content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document');ext='docx'
        elif output=='csv':
            stream=io.StringIO();writer=csv.writer(stream)
            writer.writerow(['Draft for RA Review','예시 제품 자료' if revision.draft.snapshot['specification'].get('example') else '',revision.number,svc.effective_state(request.user,revision)])
            writer.writerow(['section','body','document_version','review_state','source_kind','source_document_id','source_version','clause','excerpt','official_url','collected_at'])
            for row in revision.draft.snapshot['rows']:
                for ref in row.get('search_references') or [{}]:writer.writerow([csv_cell(value) for value in [row['section'],row.get('body',''),revision.number,svc.effective_state(request.user,revision),ref.get('kind',''),ref.get('document_id',''),ref.get('version',''),ref.get('section',''),ref.get('text',''),ref.get('official_url',''),ref.get('collected_at','')]])
            response=HttpResponse(('\ufeff'+stream.getvalue()).encode('utf-8'),content_type='text/csv; charset=utf-8');ext='csv'
        else:raise Http404
        response['Content-Disposition']=f'attachment; filename="ra-document-{revision.document_id}-v{revision.number}.{ext}"';return response
    if request.method=='POST':
        try:
            data=input_data(request);action=data.get('action')
            if action=='revise':
                snapshot=svc.edited_snapshot(request.user,revision,data)
                revision=svc.save_revision(request.user,revision.document,snapshot,data.get('reason',''),data.get('expected',0))
                if api:return JsonResponse({'revision_id':revision.pk,'number':revision.number},status=201)
                return redirect('market-ra-document',pk=revision.pk)
            elif action=='refresh':
                snapshot=svc.prepare_snapshot(revision.document.project,revision.document.document_type,revision.document.language)
                before={row['section']:row for row in revision.draft.snapshot['rows']}
                for row in snapshot['rows']:
                    old=before.get(row['section'],{})
                    row['body']=old.get('body',row['body']);row['search_references']=old.get('search_references',[])
                refreshed=svc.save_revision(request.user,revision.document,snapshot,data.get('reason',''),data.get('expected',0))
                if api:return JsonResponse({'revision_id':refreshed.pk,'number':refreshed.number},status=201)
                return redirect('market-ra-document',pk=refreshed.pk)
            elif action=='validate':svc.validate(request.user,revision)
            elif action=='review':svc.review(request.user,revision,data.get('state',''),data.get('reason',''),data.get('expected_review',0),data.get('acknowledged') in (True,'on','true'))
            else:raise ValidationError('동작을 확인하세요.')
        except (ValidationError,ValueError,TypeError) as exc:error=str(exc);status=400
    findings=list(revision.validations.order_by('-pk'));latest=findings[0] if findings else None
    prior=revision.document.revisions.filter(number__lt=revision.number).select_related('draft').order_by('-number').first()
    changes=[]
    if prior:
        before={r['section']:r for r in prior.draft.snapshot['rows']}
        for row in revision.draft.snapshot['rows']:
            old=before.get(row['section'],{})
            if old!=row:changes.append({'section':row['section'],'diff':'\n'.join(difflib.unified_diff(old.get('body','').splitlines(),row.get('body','').splitlines(),fromfile='previous',tofile='current',lineterm='')) or '근거·대상 모델 변경'})
    events=list(revision.review_events.select_related('actor').order_by('-pk'));state=svc.effective_state(request.user,revision)
    source_impacts=svc.impacts(request.user,revision)
    if api:return JsonResponse({'revision_id':revision.pk,'number':revision.number,'state':state,'snapshot':revision.draft.snapshot,'validation':latest.findings if latest else None,'validation_id':latest.pk if latest else None,'validation_history':[{'id':v.pk,'at':v.created_at.isoformat(),'actor_id':v.actor_id,'findings':v.findings} for v in findings],'versions':[{'id':v.pk,'number':v.number,'reason':v.reason} for v in revision.document.revisions.order_by('-number')],'review_events':[{'id':e.pk,'state':e.state,'reason':e.reason,'actor_id':e.actor_id,'at':e.created_at.isoformat()} for e in events],'changes':changes,'source_impacts':[{'section':i['section'],'state':i['state'],'fingerprint':i['fingerprint'],'snapshot':i['snapshot']} for i in source_impacts],'error':error},status=status,json_dumps_params={'ensure_ascii':False})
    adoptions=svc.selectable_adoptions(request.user,revision.document.project)
    for row in revision.draft.snapshot['rows']:
        row['ref_choices']=[{'id':a.pk,'label':str(a.pk)+' / '+a.snapshot['title']+' / '+a.snapshot['version']+' / '+a.snapshot['section'],'selected':a.pk in [r.get('adoption_id') for r in row.get('search_references',[])]} for a in adoptions]
    return render(request,'pms/markets/ra_document.html',{'revision':revision,'document':revision.document,'rows':revision.draft.snapshot['rows'],'versions':revision.document.revisions.order_by('-number'),'validations':findings,'validation':latest,'previous_validation':findings[1] if len(findings)>1 else None,'events':events,'expected_review':events[0].pk if events else 0,'state':state,'states':svc.STATES,'changes':changes,'impacts':source_impacts,'error':error},status=status)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def impact_list(request,api=False):
    items=[];available=candidates(request.user,include_history=True)
    for revision in RADocumentRevision.objects.filter(document__in=svc.visible_documents(request.user)).select_related('document__project__device','draft'):
        if svc.revision_access(request.user,revision):
            for item in svc.impacts(request.user,revision):items.append({**item,'revision':revision,'adoption':None,'target':'revision','id':revision.pk})
    for adoption in SearchEvidenceAdoption.objects.select_related('review__result__run','draft__project__device'):
        if adoption_access(request.user,adoption):
            change=svc.change_for(request.user,adoption.snapshot,available)
            if change:
                event=adoption.impact_events.filter(fingerprint=change['fingerprint']).order_by('-pk').first()
                items.append({**change,'revision':None,'adoption':adoption,'section':adoption.snapshot['section'],'state':event.state if event else 'REVIEW_REQUIRED','event':event,'history':list(adoption.impact_events.select_related('actor').order_by('-pk')),'target':'adoption','id':adoption.pk})
    error='';status=200
    if request.method=='POST':
        try:
            data=input_data(request)
            selected=next((i for i in items if i['target']==data.get('target') and str(i['id'])==str(data.get('id')) and i['section']==data.get('section') and i['fingerprint']==data.get('fingerprint')),None)
            if not selected:raise Http404
            if data.get('state') not in svc.IMPACT_STATES or not data.get('reason','').strip() or len(data['reason'])>2000:raise ValidationError('영향 검토 상태와 사유를 입력하세요.')
            with transaction.atomic():
                if selected['revision']:RADocument.objects.select_for_update().get(pk=selected['revision'].document_id)
                else:SearchEvidenceAdoption.objects.select_for_update().get(pk=selected['adoption'].pk)
                qs=RASourceImpactReview.objects.filter(revision=selected['revision'],adoption=selected['adoption'],section=selected['section'],fingerprint=selected['fingerprint'])
                latest=qs.order_by('-pk').first()
                if int(data.get('expected',0))!=(latest.pk if latest else 0):raise ValidationError('영향 검토 이력이 변경됐습니다. 다시 확인하세요.')
                event=RASourceImpactReview.objects.create(revision=selected['revision'],adoption=selected['adoption'],actor=request.user,section=selected['section'],fingerprint=selected['fingerprint'],state=data['state'],reason=data['reason'],snapshot=selected['snapshot'])
                audit(request.user,'RA_SOURCE_IMPACT_REVIEW',event,after={'revision_id':selected['revision'].pk if selected['revision'] else None,'state':event.state})
            if api:return JsonResponse({'id':event.pk,'state':event.state},status=201)
            return redirect('market-ra-impacts')
        except (ValidationError,ValueError,TypeError) as exc:error=str(exc);status=400
    if api:return JsonResponse({'items':[{'target':i['target'],'id':i['id'],'section':i['section'],'fingerprint':i['fingerprint'],'state':i['state'],'snapshot':i['snapshot']} for i in items],'error':error},status=status)
    return render(request,'pms/markets/ra_impacts.html',{'items':items,'error':error,'states':svc.IMPACT_STATES},status=status)
