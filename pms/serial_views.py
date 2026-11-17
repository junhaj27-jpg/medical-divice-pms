"""Read-only UDI snapshots and append-only label PMS records; never a barcode encoder."""
import json
from uuid import uuid4
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction, OperationalError
from django.db.models import Q
from django.http import JsonResponse, Http404, FileResponse
from io import BytesIO
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .gs1 import validate_gtin14,compare_label
from .market_views import market_view,device_for
from .market_service import allowed_markets,scoped
from .market_models import ProductMarket
from .serial_models import (ManufacturingSerial,SerialDispatchRecord,UDILabelIncident,
    UDILabelIncidentDispatch,UDILabelIncidentEvidence,UDILabelFollowup)
from .serial_service import issue_serial,lock_namespace,sync_legacy
from .models import Attachment,RegulatoryProfile,BusinessPartner,WorkTask
from .services import audit,visible_complaints
from .workflow import save_task


class IssueForm(forms.Form):
    gtin_snapshot=forms.CharField(max_length=14,validators=[validate_gtin14],widget=forms.HiddenInput)
    manufactured_on=forms.DateField(label='실제 제조일',widget=forms.DateInput(attrs={'type':'date'}))
    request_key=forms.UUIDField(widget=forms.HiddenInput)

class GTINForm(forms.Form):
    gtin_14=forms.CharField(label='GTIN-14',max_length=14,validators=[validate_gtin14])

class DispatchForm(forms.Form):
    dispatched_on=forms.DateField(label='실제 출고일',widget=forms.DateInput(attrs={'type':'date'}))
    reference=forms.CharField(label='출고 참조번호',max_length=120)
    printed_udi=forms.CharField(label='출고 라벨 UDI',max_length=500,required=False)
    note=forms.CharField(label='출고 메모',max_length=2000,required=False)

def evidence_for(user,device):
    profile=Q(ra_profile__device=device)
    if scoped(user):profile &= Q(ra_profile__jurisdiction__in=allowed_markets(user))
    return Attachment.objects.filter(profile|Q(complaint__in=visible_complaints(user).filter(device=device)),scan_status='PASSED').distinct()

def profiles_for(user,device):
    qs=RegulatoryProfile.objects.filter(device=device)
    return qs.filter(jurisdiction__in=allowed_markets(user)) if scoped(user) else qs

class IncidentForm(forms.Form):
    printed_udi=forms.CharField(label='라벨에 인쇄된 UDI',max_length=500)
    scan_value=forms.CharField(label='스캔값 (선택)',max_length=500,required=False)
    profile=forms.ModelChoiceField(label='RA·QA 검토 관할',queryset=RegulatoryProfile.objects.none())
    dispatches=forms.ModelMultipleChoiceField(label='영향받은 출고 기록',queryset=SerialDispatchRecord.objects.none(),required=False)
    evidence=forms.ModelMultipleChoiceField(label='증빙 (검사 통과 첨부)',queryset=Attachment.objects.none(),required=False)
    label_version=forms.ModelChoiceField(label='관련 라벨 버전 (선택)',queryset=None,required=False)
    due_at=forms.DateTimeField(label='내부 검토 업무 기한 (보고 기한과 별도)',widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))
    def __init__(self,*args,user,serial,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['profile'].queryset=profiles_for(user,serial.device)
        self.fields['dispatches'].queryset=serial.dispatches.all()
        self.fields['evidence'].queryset=evidence_for(user,serial.device)
        from .models import LabelVersion
        self.fields['label_version'].queryset=LabelVersion.objects.filter(profile__in=profiles_for(user,serial.device))

class FollowupForm(forms.Form):
    action_type=forms.ChoiceField(label='후속 조치',choices=UDILabelFollowup._meta.get_field('action_type').choices)
    rationale=forms.CharField(label='조치·검토 사유',max_length=4000,widget=forms.Textarea)
    corrected_udi=forms.CharField(label='정정 라벨 UDI (선택)',max_length=500,required=False)
    status=forms.ChoiceField(label='연결 검토 업무 상태',choices=WorkTask.Status.choices)
    previous=forms.IntegerField(min_value=0,widget=forms.HiddenInput)

def serial_for(request,device,pk):
    # A cloned product never gains access to somebody else's issued record.
    return get_object_or_404(ManufacturingSerial.objects.filter(device=device),pk=pk)

def payload(record,created=False):
    return dict(id=record.pk,created=created,gtin=record.gtin_14,manufactured_on=str(record.manufactured_on or ''),serial=record.serial_number,udi=record.expected_udi,
        hri=record.expected_udi,barcode_encoded_data=None,barcode_generation_supported=False,status=record.status)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def serials(request,pk,api=False):
    device=device_for(request,pk); status=200
    form=IssueForm(initial={'gtin_snapshot':device.gtin_14,'request_key':uuid4()})
    gtin_form=GTINForm(initial={'gtin_14':device.gtin_14})
    if request.method=='POST':
        data=request.POST
        if api:
            try:data=json.loads(request.body)
            except (ValueError,UnicodeDecodeError):return JsonResponse({'error':'invalid_json'},status=400)
            if not isinstance(data,dict):return JsonResponse({'error':'invalid_input'},status=400)
            if any(key in data and not isinstance(data[key],str) for key in ('gtin_snapshot','manufactured_on','request_key')):
                return JsonResponse({'error':'invalid_input_types'},status=400)
        if not api and data.get('action')=='profile':
            code=data.get('market')
            if code not in allowed_markets(request.user):raise Http404
            if scoped(request.user) and not ProductMarket.objects.filter(device=device,market=code).exists():raise Http404
            from .ra_services import save_record
            with transaction.atomic():
                device=device_for(request,pk,lock=True)
                if not profiles_for(request.user,device).filter(jurisdiction=code).exists():
                    organization,_=BusinessPartner.objects.get_or_create(name=device.manufacturer.name)
                    save_record(RegulatoryProfile(),request.user,dict(device=device,jurisdiction=code,organization=organization,organization_role='MANUFACTURER',title=f'UDI 라벨 검토 · {device.model_number}',owner=request.user,is_example=device.model_number.startswith('DEMO-')),'UDI 라벨 PMS 검토 관할 등록')
            return redirect('market-serials',pk)
        if not api and data.get('action')=='gtin':
            gtin_form=GTINForm(data)
            if gtin_form.is_valid():
                with transaction.atomic():
                    lock_namespace(gtin_form.cleaned_data['gtin_14'])
                    device=device_for(request,pk,lock=True);before=device.gtin_14
                    device.gtin_14=gtin_form.cleaned_data['gtin_14'];device.save(update_fields=['gtin_14'])
                    sync_legacy(device.gtin_14)
                    audit(request.user,'DEVICE_GTIN',device,before={'gtin':before},after={'gtin':device.gtin_14})
                return redirect('market-serials',pk)
            status=400
        else:
            form=IssueForm(data)
            if form.is_valid():
                try:
                    record,created=issue_serial(request.user,device,**form.cleaned_data)
                    if api:return JsonResponse(payload(record,created),status=201 if created else 200)
                    return redirect('market-serial',pk,record.pk)
                except ValidationError as exc:form.add_error(None,exc);status=400
                except OperationalError:
                    form.add_error(None,'DB가 사용 중입니다. 같은 요청 키로 다시 전송하세요.');status=503
            else:status=400
            if api:return JsonResponse({'errors':form.errors.get_json_data()},status=status)
    if api:return JsonResponse({'error':'post_required'},status=405)
    markets=(ProductMarket.objects.filter(device=device,market__in=allowed_markets(request.user)).values_list('market',flat=True)
             if scoped(request.user) else allowed_markets(request.user))
    return render(request,'pms/markets/serials.html',dict(device=device,form=form,gtin_form=gtin_form,profile_markets=markets,rows=device.manufacturing_serials.select_related('device','issued_by').prefetch_related('lot_references')[:100]),status=status)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def detail(request,pk,serial_id):
    device=device_for(request,pk);serial=serial_for(request,device,serial_id);result=None;status=200
    dispatch=DispatchForm();incident=IncidentForm(user=request.user,serial=serial)
    if request.method=='POST':
        action=request.POST.get('action')
        if not serial.expected_udi:return render(request,'pms/ra/error.html',{'error':'GTIN·제조일 또는 기존 중복을 먼저 RA가 확인해야 합니다.'},status=400)
        if action=='validate':
            value=request.POST.get('printed_udi','')
            if len(value)>500:status=400
            else:result=compare_label(value,serial.gtin_14,serial.manufactured_on,serial.serial_number)
        elif action=='dispatch':
            dispatch=DispatchForm(request.POST)
            if dispatch.is_valid():
                with transaction.atomic():
                    row=SerialDispatchRecord.objects.create(serial=serial,expected_udi=serial.expected_udi,recorded_by=request.user,**dispatch.cleaned_data)
                    audit(request.user,'UDI_DISPATCH',row,after={'serial_id':serial.pk})
                return redirect('market-serial',pk,serial_id)
            status=400
        elif action=='incident':
            incident=IncidentForm(request.POST,user=request.user,serial=serial)
            if incident.is_valid():
                from .file_security import safe_attachment_bytes
                values=incident.cleaned_data
                try:
                    with transaction.atomic():
                        for attachment in values['evidence']:safe_attachment_bytes(attachment)
                        task=save_task(WorkTask(ra_profile=values['profile'],assignee=request.user,title=f'UDI 라벨 PMS 검토 · #{serial.pk}',description='제조번호 라벨 오류 기록에서 원본과 차이를 확인하세요.',due_at=values['due_at']),request.user)
                        diffs={'printed':compare_label(values['printed_udi'],serial.gtin_14,serial.manufactured_on,serial.serial_number)}
                        if values['scan_value']:diffs['scan']=compare_label(values['scan_value'],serial.gtin_14,serial.manufactured_on,serial.serial_number)
                        row=UDILabelIncident.objects.create(serial=serial,printed_udi=values['printed_udi'],scan_value=values['scan_value'],expected_udi=serial.expected_udi,differences=diffs,task=task,label_version=values['label_version'],recorded_by=request.user)
                        for item in values['dispatches']:
                            UDILabelIncidentDispatch.objects.create(incident=row,dispatch=item,original={'id':item.pk,'dispatched_on':str(item.dispatched_on),'reference':item.reference,'expected_udi':item.expected_udi,'printed_udi':item.printed_udi})
                        for item in values['evidence']:
                            UDILabelIncidentEvidence.objects.create(incident=row,attachment=item,original={'id':item.pk,'sha256':item.sha256,'name':item.original_name})
                        audit(request.user,'UDI_LABEL_PMS',row,after={'serial_id':serial.pk,'task_id':task.pk})
                    return redirect('market-udi-incident',pk,row.pk)
                except ValidationError as exc:incident.add_error(None,exc)
            status=400
        else:status=400
    return render(request,'pms/markets/serial_detail.html',dict(device=device,serial=serial,result=result,dispatch_form=dispatch,incident_form=incident,
        lot_references=serial.lot_references.filter(lot__device=device),incidents=serial.label_incidents.filter(task__ra_profile__in=profiles_for(request.user,device))),status=status)

def incident_for(request,device,pk):
    incident=get_object_or_404(UDILabelIncident,pk=pk,serial__device=device,task__ra_profile__in=profiles_for(request.user,device))
    if incident.evidence_links.exclude(attachment__in=evidence_for(request.user,device)).exists():raise Http404
    if incident.label_version_id and incident.label_version.profile_id not in profiles_for(request.user,device).values_list('pk',flat=True):raise Http404
    return incident

@market_view
@never_cache
@require_http_methods(['GET'])
def incident_evidence(request,pk,incident_id,attachment_id):
    device=device_for(request,pk);incident=incident_for(request,device,incident_id)
    link=get_object_or_404(incident.evidence_links,attachment_id=attachment_id)
    if link.attachment.sha256!=link.original['sha256']:raise Http404
    from .file_security import safe_attachment_bytes,normalized_name
    return FileResponse(BytesIO(safe_attachment_bytes(link.attachment)),as_attachment=True,filename=normalized_name(link.original['name'] or 'evidence.txt'))

class EvidenceUploadForm(forms.Form):
    profile=forms.ModelChoiceField(label='RA 검토 관할',queryset=RegulatoryProfile.objects.none())
    file=forms.FileField(label='라벨 오류 증빙 (PDF·PNG·JPEG·TXT·CSV)')

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def upload(request,pk,serial_id):
    device=device_for(request,pk);serial=serial_for(request,device,serial_id)
    form=EvidenceUploadForm(request.POST or None,request.FILES or None)
    form.fields['profile'].queryset=profiles_for(request.user,device)
    if form.is_valid():
        from .file_security import normalized_name,scan_attachment
        try:
            file=form.cleaned_data['file']
            obj=Attachment(ra_profile=form.cleaned_data['profile'],file=file,original_name=normalized_name(file.name),uploaded_by=request.user)
            obj.full_clean();obj.save();scan_attachment(obj,request.user)
            if obj.scan_status=='PASSED':return redirect('market-serial',pk,serial_id)
            form.add_error(None,'파일 검사 미통과: 증빙으로 연결할 수 없습니다. 관리자에게 검사 설정을 확인하세요.')
        except ValidationError as exc:form.add_error(None,exc)
    return render(request,'pms/serial_upload.html',{'form':form},status=400 if request.method=='POST' else 200)

@market_view
@never_cache
@require_http_methods(['GET','POST'])
def incident_detail(request,pk,incident_id):
    device=device_for(request,pk)
    incident=incident_for(request,device,incident_id)
    previous=incident.followups.order_by('-pk').values_list('pk',flat=True).first() or 0
    form=FollowupForm(initial={'previous':previous,'status':incident.task.status});status=200
    if request.method=='POST':
        form=FollowupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                WorkTask.objects.select_for_update().get(pk=incident.task_id)
                latest=incident.followups.order_by('-pk').values_list('pk',flat=True).first() or 0
                if latest!=form.cleaned_data['previous']:
                    form.add_error(None,'다른 검토자가 저장했습니다. 최신 이력을 다시 열어 확인하세요.');status=409
                else:
                    values=form.cleaned_data.copy();values.pop('previous');new_status=values.pop('status')
                    row=UDILabelFollowup.objects.create(incident=incident,actor=request.user,**values)
                    task=WorkTask.objects.get(pk=incident.task_id);task.status=new_status;save_task(task,request.user)
                    audit(request.user,'UDI_LABEL_FOLLOWUP',row,after={'incident_id':incident.pk,'status':new_status})
                    return redirect('market-udi-incident',pk,incident_id)
        else:status=400
    return render(request,'pms/markets/udi_incident.html',dict(device=device,incident=incident,form=form),status=status)
