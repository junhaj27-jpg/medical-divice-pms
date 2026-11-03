"""A shared UI shell over explicit domain forms; all mutations use RA services."""
import json
from django import forms
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from . import ra_services as s
from .models import Attachment, AuditLog
from .file_security import normalized_name,scan_attachment,safe_attachment_bytes


def entry(kind):
    from django.http import Http404
    if kind not in s.REGISTRY: raise Http404
    return s.REGISTRY[kind]


def form_class(model):
    from .ra_operations import OPERATION_MODELS
    excluded=s.SYSTEM_FIELDS | ({'baseline','confirmed_trace','components','excerpt','line_number','submission_manifest'} if model in OPERATION_MODELS else set())
    fields=[f.name for f in model._meta.fields if f.name not in excluded]
    fields += [f.name for f in model._meta.many_to_many]
    return forms.modelform_factory(model,fields=fields)


@login_required
def dashboard(request):
    s.require_ra(request.user)
    counts=[(key,label,model.objects.count()) for key,(model,label) in s.REGISTRY.items()]
    return render(request,'pms/ra/dashboard.html',{'counts':counts})


@login_required
def listing(request,kind):
    s.require_ra(request.user);model,label=entry(kind)
    qs=model.objects.order_by('-pk')
    if request.GET.get('profile') and any(field.name=='profile' for field in model._meta.fields):
        try: qs=qs.filter(profile_id=int(request.GET['profile']))
        except ValueError: return HttpResponse('올바른 프로필 번호가 필요합니다.',status=400)
    q=request.GET.get('q','').strip()[:120]
    if q: qs=qs.filter(title__icontains=q)
    sample=request.GET.get('sample','')
    if sample in ('real','sample'): qs=qs.filter(is_example=sample=='sample')
    page=Paginator(qs,50).get_page(request.GET.get('page'))
    params=request.GET.copy();params.pop('page',None)
    return render(request,'pms/ra/list.html',{'items':page,'page':page,'params':params.urlencode(),'label':label,'kind':kind,'q':q,'sample':sample})


@login_required
def edit(request,kind,pk=None):
    s.require_ra(request.user);model,label=entry(kind)
    if kind=='meeting-candidates' and not pk: return HttpResponse('회의록에서 후보를 추출하세요.',status=405)
    obj=get_object_or_404(model,pk=pk) if pk else model()
    # Model save is service-only; ModelForm validation does not write.
    form=form_class(model)(request.POST or None,instance=obj,initial={'owner':request.user.pk})
    if request.method=='POST' and form.is_valid():
        try:
            values={k:v for k,v in form.cleaned_data.items() if k in {f.name for f in model._meta.concrete_fields}-s.SYSTEM_FIELDS}
            links={f.name:form.cleaned_data[f.name] for f in model._meta.many_to_many}
            saved=s.save_record(obj,request.user,values,request.POST.get('reason',''),request.POST.get('revision'),links)
            return redirect('ra-detail',kind=kind,pk=saved.pk)
        except (ValidationError,ValueError,TypeError) as exc: form.add_error(None,str(exc))
    return render(request,'pms/ra/form.html',{'form':form,'item':obj,'kind':kind,'label':label})


@login_required
def detail(request,kind,pk):
    s.require_ra(request.user);model,label=entry(kind);obj=get_object_or_404(model,pk=pk)
    from .ra_operations import dashboard_context
    operational=dashboard_context(obj)
    fields=[(f.verbose_name,getattr(obj,f.name)) for f in model._meta.fields if f.name not in ('approval_snapshot','frozen_snapshot')]
    history=AuditLog.objects.filter(object_type=model.__name__,object_id=str(pk)).order_by('-pk')[:100]
    return render(request,'pms/ra/detail.html',{'item':obj,'fields':fields,'history':history,'kind':kind,'label':label,'snapshot':json.dumps(obj.approval_snapshot,ensure_ascii=False,indent=2),'actions':s.available_actions(obj,request.user),'available_evidence':Attachment.objects.filter(ra_profile_id=getattr(obj,'profile_id',obj.pk if kind=='profiles' else None),scan_status='PASSED').order_by('-pk')[:200],'operational':operational,'comparison':s.compare_documents(obj),'management_snapshot':json.dumps(getattr(obj,'management_snapshot',{}),ensure_ascii=False,indent=2),'training_impact':s.training_impact(obj) if kind=='profiles' else []})


@login_required
@require_POST
def action(request,kind,pk):
    s.require_ra(request.user);model,_=entry(kind);obj=get_object_or_404(model,pk=pk)
    try:
        from . import ra_operations as operations
        operation=request.POST.get('action')
        reason=request.POST.get('reason','')
        if kind=='quality-documents' and operation=='template':
            document=operations.template_draft(obj,request.user,request.POST.get('confirmation',''),reason)
            return redirect('ra-detail',kind='documents',pk=document.pk)
        if kind=='meeting-sources' and operation=='extract':
            operations.extract(obj,request.user)
            return redirect('ra-list',kind='meeting-candidates')
        if kind=='meeting-candidates' and operation=='confirm':
            trace=operations.confirm(obj,request.user,reason)
            return redirect('ra-detail',kind='design-traces',pk=trace.pk)
        if kind=='dhf-baselines' and operation=='baseline':
            operations.capture(obj,request.user,reason)
            return redirect('ra-detail',kind=kind,pk=pk)
        if kind=='security-inventories' and operation=='sbom':
            operations.import_sbom(obj,request.user,reason)
            return redirect('ra-detail',kind=kind,pk=pk)
        if request.POST.get('action')=='sync-training' and kind=='training-requirements':
            s.sync_training(obj,request.user)
            return redirect('ra-detail',kind=kind,pk=pk)
        if request.POST.get('action')=='capture' and kind=='management-reviews':
            s.capture_management_review(obj,request.user,request.POST.get('reason',''),request.POST.get('revision'))
            return redirect('ra-detail',kind=kind,pk=pk)
        if request.POST.get('action')=='contact' and kind=='field-recipients':
            file=get_object_or_404(Attachment,pk=request.POST['evidence']) if request.POST.get('evidence') else None
            s.record_field_contact(obj,request.user,request.POST.get('method',''),request.POST.get('note',''),file)
            return redirect('ra-detail',kind=kind,pk=pk)
        if request.POST.get('action')=='evaluate' and kind=='field-actions':
            file=get_object_or_404(Attachment,pk=request.POST.get('evidence'))
            s.evaluate_field_action(obj,request.user,request.POST.get('verdict'),request.POST.get('reason',''),file)
            return redirect('ra-detail',kind=kind,pk=pk)
        if request.POST.get('action')=='revise' and kind=='documents':
            new=s.revise_document(obj,request.user,request.POST.get('reason',''))
            return redirect('ra-detail',kind=kind,pk=new.pk)
        if request.POST.get('action')=='schedule':
            from datetime import date
            s.schedule_task(obj,request.user,date.fromisoformat(request.POST.get('due_on','')))
        else: s.transition(obj,request.user,request.POST.get('action'),request.POST.get('reason',''),request.POST.get('revision'),details={'confirmation':request.POST.get('confirmation','')})
    except (ValidationError,ValueError,TypeError) as exc: return render(request,'pms/ra/error.html',{'error':str(exc)},status=400)
    return redirect('ra-detail',kind=kind,pk=pk)


@login_required
def api_collection(request,kind,pk=None):
    s.require_ra(request.user);model,_=entry(kind)
    if request.method=='GET':
        if pk:
            obj=get_object_or_404(model,pk=pk);return JsonResponse({'id':obj.pk,'revision':obj.revision,'state':obj.state,'content':s.snapshot(obj),'approval_snapshot':obj.approval_snapshot})
        return JsonResponse({'items':list(model.objects.order_by('-pk').values('id','title','state','revision')[:200])})
    if request.method!='POST': return JsonResponse({'error':'GET/POST only; deletion disabled'},status=405)
    try:
        payload=json.loads(request.body)
        if not isinstance(payload,dict) or not isinstance(payload.get('data',{}),dict): raise ValidationError('JSON 객체를 입력하세요.')
        if not isinstance(payload.get('reason',''),str) or not isinstance(payload.get('details') or {},dict): raise ValidationError('처리 사유와 상세 값의 형식을 확인하세요.')
        if any(key in payload.get('data',{}) for key in s.SYSTEM_FIELDS): raise ValidationError('시스템 필드는 직접 지정할 수 없습니다.')
        if kind=='meeting-candidates' and not pk: return JsonResponse({'error':'회의록에서 후보를 추출하세요.'},status=405)
        obj=get_object_or_404(model,pk=pk) if pk else model()
        if payload.get('action'):
            if not pk: raise ValidationError('기존 기록을 선택하세요.')
            obj=s.transition(obj,request.user,payload['action'],payload.get('reason',''),payload.get('revision'),details=payload.get('details'))
        else:
            form=form_class(model)(payload.get('data',{}),instance=obj)
            if not form.is_valid(): return JsonResponse({'errors':form.errors.get_json_data()},status=400)
            values={f.name:form.cleaned_data[f.name] for f in model._meta.concrete_fields if f.name in form.cleaned_data}
            links={f.name:form.cleaned_data[f.name] for f in model._meta.many_to_many}
            obj=s.save_record(obj,request.user,values,payload.get('reason',''),payload.get('revision'),links)
        return JsonResponse({'id':obj.pk,'revision':obj.revision,'state':obj.state},status=200 if pk else 201)
    except (ValueError,TypeError,ValidationError) as exc: return JsonResponse({'error':str(exc)},status=400)


@login_required
def evidence_upload(request,profile_id):
    from .ra_models import RegulatoryProfile
    s.require_ra(request.user);profile=get_object_or_404(RegulatoryProfile,pk=profile_id)
    class Upload(forms.Form): file=forms.FileField(label='RA 증빙 (검사 전 사용 불가)')
    form=Upload(request.POST or None,request.FILES or None)
    if request.method=='POST' and form.is_valid():
        obj=Attachment(ra_profile=profile,file=form.cleaned_data['file'],original_name=normalized_name(form.cleaned_data['file'].name),uploaded_by=request.user)
        try:
            obj.full_clean();obj.save();scan_attachment(obj,request.user)
            return redirect('ra-evidence',pk=obj.pk)
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'pms/form.html',{'form':form,'title':'제품 RA 증빙 등록'})


@login_required
def evidence_download(request,pk):
    s.require_ra(request.user);obj=get_object_or_404(Attachment,pk=pk)
    if request.GET.get('download')=='1':
        from io import BytesIO
        return FileResponse(BytesIO(safe_attachment_bytes(obj)),as_attachment=True,filename=obj.original_name)
    return render(request,'pms/ra/evidence.html',{'item':obj})


@login_required
def my_training(request,pk=None):
    from .ra_models import TrainingAssignment
    if pk:
        obj=get_object_or_404(TrainingAssignment,pk=pk,trainee=request.user)
        if request.GET.get('file')=='1':
            if not obj.requirement.document.primary_file_id: return HttpResponse('본문 자료입니다.',status=404)
            from io import BytesIO
            file=obj.requirement.document.primary_file
            return FileResponse(BytesIO(safe_attachment_bytes(file)),as_attachment=True,filename=file.original_name)
        return render(request,'pms/ra/my_training.html',{'item':obj})
    return render(request,'pms/ra/my_training.html',{'items':TrainingAssignment.objects.filter(trainee=request.user).select_related('requirement__document')})


@login_required
def management_export(request,pk):
    from .ra_models import ManagementReview
    s.require_ra(request.user);obj=get_object_or_404(ManagementReview,pk=pk)
    return JsonResponse({'title':obj.title,'revision':obj.revision,'reviewer_id':obj.reviewer_id,'author_id':obj.created_by_id,'data':obj.management_snapshot},json_dumps_params={'ensure_ascii':False})


@login_required
def package_download(request,kind,pk):
    s.require_ra(request.user)
    if kind not in ('packages','audit-packages'): return HttpResponse(status=404)
    model,_=entry(kind);obj=get_object_or_404(model,pk=pk)
    try: data=s.package_bytes(obj,request.user)
    except ValidationError as exc: return render(request,'pms/ra/error.html',{'error':str(exc)},status=400)
    from io import BytesIO
    return FileResponse(BytesIO(data),as_attachment=True,filename=f'RA-{kind}-{obj.pk}-v{obj.version}.zip')

@login_required
def dhf_export(request,kind,pk):
    from .ra_operations import matrix
    from .ra_operations_models import DHFProject,DHFBaseline
    from .reporting import build_pdf
    import csv
    s.require_ra(request.user)
    if kind=='dhf-projects':
        obj=get_object_or_404(DHFProject,pk=pk)
        data=matrix(obj)
    elif kind=='dhf-baselines':
        obj=get_object_or_404(DHFBaseline,pk=pk)
        data=obj.baseline
    else:
        return HttpResponse(status=404)
    fmt=request.GET.get('format','csv')
    if fmt=='pdf':
        # Use the existing escaped Korean PDF renderer and font configuration.
        payload={key:[] for key in ('risk','regulatory_reports','tasks','capas','recalls','rules','evidence')}
        payload['complaint']={'title':'DHF 연결·검토 현황', 'matrix':data}
        try:
            pdf=build_pdf(payload,f'DHF-{obj.pk}',obj.revision,request.user.username,[],title='DHF 추적 매트릭스')
        except ValidationError as exc:
            return HttpResponse(str(exc),status=400)
        response=HttpResponse(pdf,content_type='application/pdf')
    elif fmt=='csv':
        response=HttpResponse('\ufeff',content_type='text/csv; charset=utf-8')
        writer=csv.writer(response)
        writer.writerow(['프로젝트','출시 버전','추적 행','제목','관계','대상','상태','원문','증빙','구버전'])
        def spreadsheet_text(value):
            value=str(value)
            return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value
        for row in data.get('rows',[]):
            for relation,linked in row['links'].items():
                linked=linked or {}
                writer.writerow([data['project'],spreadsheet_text(data.get('release_version',data['release'])),row['id'],spreadsheet_text(row['title']),relation,
                                 spreadsheet_text(linked.get('title','')),linked.get('state','누락'),linked.get('url',''),
                                 ','.join(str(file['id']) for file in linked.get('evidence',[])),linked.get('obsolete',False)])
    else:
        return HttpResponse(status=400)
    response['Content-Disposition']=f'attachment; filename="DHF-{obj.pk}.{fmt}"'
    return response

@login_required
def quality_summary(request):
    from django.utils import timezone
    from .ra_operations_models import QualityDocument,QualityRecord
    s.require_ra(request.user)
    example=request.GET.get('sample')=='1'
    records=QualityRecord.objects.filter(is_example=example).order_by('due_on','pk')
    documents=QualityDocument.objects.filter(is_example=example).select_related('document')
    today=timezone.localdate()
    pending=records.exclude(state__in=['APPROVED','CANCELLED','CLOSED'])
    overdue=pending.filter(due_on__lt=today)
    due_documents=documents.filter(document__state='EFFECTIVE',document__next_review_on__lt=today)
    unapproved=documents.exclude(state__in=['APPROVED','RETIRED','CANCELLED'])
    context={
        'example':example, 'empty_count':pending.filter(values={}).count(),
        'overdue_count':overdue.count(), 'overdue':overdue[:100],
        'doc_count':due_documents.count(), 'due_documents':due_documents[:100],
        'unapproved_count':unapproved.count(), 'unapproved':unapproved[:100],
    }
    return render(request,'pms/ra/quality_summary.html',context)
