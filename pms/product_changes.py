"""Freeze references on request; human market decisions never modify product masters."""
import json,uuid
from copy import deepcopy
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction,connection
from django.forms.models import model_to_dict
from .models import MedicalDevice,Attachment,ControlledDocument,WorkTask
from .market_models import EU_COUNTRIES,ProductMarket
from .market_service import require_workspace,allowed_markets,product_markets
from .dental_models import DentalProject,DentalDraft
from .dental_views import documents_for
from .search_history import draft_access
from .ra_models import LabelVersion
from .mri_registration import configuration_payload
from .product_change_models import MRIProductChange,MRIChangeMarket,MRIChangeDecision,MRIChangeAction
from . import review_tasks
from .file_security import safe_attachment_bytes
from .services import audit

DECISIONS={'REVIEW':'추가 검토 필요','DOCUMENT':'문서 개정 필요','EVIDENCE':'시험 증빙 보완 필요','NONE':'영향 없음'}

def plain(value):return json.loads(json.dumps(value,cls=DjangoJSONEncoder))

def can_review(user,review):
    return review.country in allowed_markets(user) and product_markets(user).filter(device_id=review.change.device_id,market=review.country).exists()

def require_review(user,review):
    require_workspace(user)
    if not can_review(user,review):raise PermissionDenied

def file_allowed(file,review):
    if not file.ra_profile_id or file.ra_profile.device_id!=review.change.device_id:return False
    return file.ra_profile.jurisdiction in (review.country,'EU' if review.country in EU_COUNTRIES else 'US')

def draft_allowed(user,draft):
    if hasattr(draft,'ra_revision'):
        from .dossier import revision_access
        return revision_access(user,draft.ra_revision)
    return draft_access(user,draft)

def candidate_access(user,review,candidate):
    if not can_review(user,review):return False
    if candidate.get('draft_id'):
        draft=DentalDraft.objects.filter(pk=candidate['draft_id']).first()
        if not draft or not draft_allowed(user,draft):return False
    if candidate.get('attachment_id'):
        file=Attachment.objects.select_related('ra_profile').filter(pk=candidate['attachment_id']).first()
        if not file or not file_allowed(file,review):return False
    return True

def require_candidate(user,review,candidate):
    require_review(user,review)
    if not candidate_access(user,review,candidate):raise PermissionDenied

def attachment_record(file):
    safe_attachment_bytes(file)
    return {'attachment_id':file.pk,'file_sha256':file.sha256,'file_name':file.original_name or '증빙 파일','file_scope':file.ra_profile.jurisdiction}

def snapshot_for(user,change,country,evidence):
    market='US' if country=='US' else 'EU'
    registration=ProductMarket.objects.get(device=change.device,market=country)
    project=DentalProject.objects.filter(device=change.device,market=market).select_related('template','guide').first()
    docs=[];tests=[]
    if project:
        drafts=list(project.drafts.order_by('-pk'))
        revisions={d.pk:getattr(d,'ra_revision',None) for d in drafts}
        seen_documents=set();legacy_added=False
        for draft in drafts:
            revision=revisions[draft.pk]
            if revision:
                if revision.document.country!=country or revision.document_id in seen_documents:continue
                seen_documents.add(revision.document_id)
            elif legacy_added:continue
            else:legacy_added=True
            if not draft_allowed(user,draft):continue
            docs.append({'key':f'draft:{draft.pk}','title':draft.snapshot.get('template',{}).get('name','RA 문서 초안'),
                'draft_id':draft.pk,'version':revision.number if revision else f'초안 ID {draft.pk}',
                'snapshot_hash':review_tasks.digest(draft.snapshot),'template':deepcopy(draft.snapshot.get('template',{})),
                'sections':[r['section'] for r in draft.snapshot.get('rows',[])],
                'why':f'제품 #{change.device_id} → {market} 작성 프로젝트 #{project.pk} → 저장된 초안 버전'})
        controlled=list(documents_for(change.device,market))
        for doc in controlled:
            row={'key':f'document:{doc.pk}','title':doc.title,'document_id':doc.pk,'version':doc.version,'record':plain(model_to_dict(doc,exclude=['evidence','tasks'])),
                 'why':f'제품 #{change.device_id} → {market} 규제 프로필 #{doc.profile_id} → 관리 문서'}
            if doc.primary_file:row.update(attachment_record(doc.primary_file))
            docs.append(row)
        for ev in project.evidence.select_related('document__primary_file').order_by('pk'):
            identity=ev.details.get('identity',[])
            file=Attachment.objects.select_related('ra_profile').filter(pk=identity[1] if len(identity)>1 else ev.document.primary_file_id,scan_status='PASSED').first()
            if not file:continue
            try:record=attachment_record(file)
            except (PermissionDenied,OSError):continue
            tests.append({'key':f'evidence:{ev.pk}','title':ev.document.number,'version':ev.document.version,'document_id':ev.document_id,
                'evidence_id':ev.pk,'record':deepcopy(ev.details),'section':ev.section,**record,
                'why':f'작성 프로젝트 #{project.pk} → {ev.section} → 제품 증빙 #{ev.pk}; 시험 모델 {ev.details.get("model","미입력")}, 소프트웨어 {ev.details.get("software_version","미입력")}; 변경 후 적용 여부는 RA 확인'})
    labels=LabelVersion.objects.filter(profile__device=change.device,profile__jurisdiction__in=[country,market]).select_related('document__primary_file')
    for label in labels:
        row={'key':f'label:{label.pk}','title':label.title,'version':label.version,'document_id':label.document_id,'record':plain(model_to_dict(label,exclude=['evidence','tasks','lots'])),
            'why':f'제품 라벨/IFU 버전 #{label.pk} → 관리 문서 #{label.document_id}'}
        if label.document.primary_file and label.document.primary_file.scan_status=='PASSED':row.update(attachment_record(label.document.primary_file))
        docs.append(row)
    selected=[]
    for file in evidence:
        scope=file.ra_profile.jurisdiction
        if scope not in (country,market):continue
        record={'key':f'attachment:{file.pk}','title':file.original_name or f'변경 신청 증빙 #{file.pk}','version':f'첨부 ID {file.pk}',**attachment_record(file),'why':'변경 접수자가 선택한 검사 통과 제품 증빙'}
        selected.append(record);tests.append(record)
    if not docs:docs=[{'key':'unresolved:documents','title':'연결된 RA 문서 없음 · 자료 확인 필요','version':'미확인','why':'등록된 시장에 연결된 작성 프로젝트·문서가 없습니다.'}]
    if not tests:tests=[{'key':'unresolved:evidence','title':'연결된 시험 증빙 없음 · 증빙 확인 필요','version':'미확인','why':'시험 적합성을 추정하지 않습니다. 시험 자료를 확인·등록하세요.'}]
    return {'registration':plain(model_to_dict(registration)),'project_id':project.pk if project else None,
        'template':{'id':project.template_id,'version':project.template.version} if project and project.template else None,
        'documents':docs,'evidence':tests,'request_evidence':selected,'notes':'후보는 연결 관계에 따른 검토 대상이며 규제 적합성·제출 필요 판단이 아닙니다.'}

@transaction.atomic
def submit(user,device,*,kind,before_value,after_value,reason,planned_on,countries,evidence_ids=(),request_key):
    review_tasks.lock(MedicalDevice,device.pk)
    require_workspace(user)
    device=MedicalDevice.objects.select_related('manufacturer').get(pk=device.pk)
    if device.product_type!='MRI':raise ValidationError('MRI 촬영 장비만 지원합니다.')
    if kind not in ('SOFTWARE','LABEL') or any(not value.strip() or len(value)>4000 for value in (before_value,after_value,reason)):raise ValidationError('변경 유형·전후 값·사유를 입력하세요.')
    if before_value.strip()==after_value.strip():raise ValidationError('변경 전후 값이 같습니다.')
    selected=list(dict.fromkeys(countries))
    available=set(product_markets(user).filter(device=device,market__in=['US',*EU_COUNTRIES]).values_list('market',flat=True))
    if not selected or not set(selected)<=available:raise PermissionDenied
    key=uuid.UUID(str(request_key))
    payload={'device_id':device.pk,'kind':kind,'before':before_value,'after':after_value,'reason':reason,'planned_on':str(planned_on),'countries':sorted(selected),'evidence_ids':sorted(set(evidence_ids))}
    hashed=review_tasks.digest(payload)
    old=MRIProductChange.objects.filter(request_key=key).first()
    if old:
        if old.requested_by_id!=user.pk or old.request_hash!=hashed:raise ValidationError('같은 접수 키를 다른 내용에 사용할 수 없습니다.')
        return old,False
    files=list(Attachment.objects.filter(pk__in=evidence_ids,scan_status='PASSED',ra_profile__device=device).select_related('ra_profile'))
    scopes=set(selected)|({'EU'} if set(selected)&set(EU_COUNTRIES) else set())
    if len(files)!=len(set(evidence_ids)) or any(f.ra_profile.jurisdiction not in scopes for f in files):raise ValidationError('선택한 시장·제품의 검사 통과 증빙만 연결하세요.')
    for file in files:safe_attachment_bytes(file)
    product=configuration_payload(device)
    if kind=='SOFTWARE' and product and product['software_version'] and product['software_version']!=before_value:raise ValidationError('변경 전 소프트웨어 버전이 등록된 MRI 구성과 다릅니다.')
    snapshot={'device':plain(model_to_dict(device)),'manufacturer':device.manufacturer.name,'configuration':product,
        'baseline_note':'소프트웨어는 등록 구성과 대조; 라벨 전후 값은 담당자 입력이며 당시 연결 라벨을 함께 확인함'}
    change=MRIProductChange.objects.create(device=device,kind=kind,before_value=before_value,after_value=after_value,reason=reason,planned_on=planned_on,requested_by=user,request_key=key,request_hash=hashed,product_snapshot=snapshot)
    for country in selected:MRIChangeMarket.objects.create(change=change,country=country,snapshot=snapshot_for(user,change,country,files))
    audit(user,'MRI_CHANGE_REQUEST',change,after={'type':kind,'markets':selected})
    return change,True

def visible_reviews(user,change=None):
    require_workspace(user)
    rows=MRIChangeMarket.objects.filter(country__in=allowed_markets(user),change__device_id__in=product_markets(user).values('device_id')).select_related('change__device')
    if change:rows=rows.filter(change=change)
    return [r for r in rows if can_review(user,r)]

def choices(user,review,category):return [r for r in review.snapshot[category] if candidate_access(user,review,r)]

@transaction.atomic
def decide(user,review,*,expected,decisions,targets,rationale,complete=False):
    # Reserve SQLite's writer before permission reads to avoid a deferred read-to-write upgrade.
    if connection.vendor=='sqlite':review_tasks.lock(MRIChangeMarket,review.pk)
    else:
        review_tasks.lock(MedicalDevice,review.change.device_id);review_tasks.lock(MRIChangeMarket,review.pk)
    review=MRIChangeMarket.objects.select_related('change__device').get(pk=review.pk)
    require_review(user,review)
    if int(expected)!=review.version:raise ValidationError('다른 담당자가 검토를 변경했습니다. 최신 이력을 다시 확인하세요.')
    selected=set(decisions)
    if not selected or not selected<=set(DECISIONS) or ('NONE' in selected and len(selected)>1):raise ValidationError('영향 없음은 다른 판단과 함께 선택할 수 없습니다.')
    if not rationale.strip() or len(rationale)>4000:raise ValidationError('판단 사유를 입력하세요.')
    normalized={}
    for flag,category in [('DOCUMENT','documents'),('EVIDENCE','evidence')]:
        keys=list(dict.fromkeys(targets.get(category,[]))) if flag in selected else []
        allowed={r['key'] for r in choices(user,review,category)}
        if flag in selected and not keys:raise ValidationError('영향받는 조치 대상을 선택하세요.')
        if not set(keys)<=allowed:raise PermissionDenied
        normalized[category]=keys
    if complete:
        if 'REVIEW' in selected:raise ValidationError('추가 검토 필요 상태는 완료할 수 없습니다.')
        expected_actions={(kind,key) for kind,category in [('DOCUMENT','documents'),('EVIDENCE','evidence')] for key in normalized[category]}
        actions=list(review.actions.select_related('task_context__task'))
        actual={(a.action_type,a.target_key):a for a in actions}
        if not expected_actions<=set(actual):raise ValidationError('선택한 대상의 후속 업무를 먼저 생성·완료하세요.')
        for action in actions:
            context=getattr(action,'task_context',None)
            if not context:raise ValidationError('후속 업무 생성이 필요합니다.')
            review_tasks.lock(WorkTask,context.task_id)
            context.task.refresh_from_db()
            if context.task.status!='DONE' or not context.completed_at:raise ValidationError('미완료 후속 업무가 있어 시장 검토를 완료할 수 없습니다.')
            proof=list(context.task.review_evidence.filter(cycle=context.cycle).select_related('attachment'))
            if not proof:raise ValidationError('업무 완료 증빙이 필요합니다.')
            for item in proof:
                if item.attachment.sha256!=item.snapshot['sha256']:raise ValidationError('완료 증빙 버전이 달라졌습니다.')
                safe_attachment_bytes(item.attachment)
    review.version+=1;review.status='COMPLETED' if complete else 'IN_REVIEW';review.save(update_fields=['version','status'])
    event=MRIChangeDecision.objects.create(review=review,actor=user,decisions=sorted(selected),targets=normalized,rationale=rationale,complete=complete,version=review.version)
    audit(user,'MRI_CHANGE_DECISION',event,after={'review':review.pk,'complete':complete,'decisions':sorted(selected)})
    return event

@transaction.atomic
def create_task(user,review,*,action_type,target_key,**task_values):
    # Reserve SQLite's writer before permission reads to avoid a deferred read-to-write upgrade.
    if connection.vendor=='sqlite':review_tasks.lock(MRIChangeMarket,review.pk)
    else:
        review_tasks.lock(MedicalDevice,review.change.device_id);review_tasks.lock(MRIChangeMarket,review.pk)
    review=MRIChangeMarket.objects.select_related('change__device').get(pk=review.pk)
    require_review(user,review)
    existing=MRIChangeAction.objects.filter(review=review,action_type=action_type,target_key=target_key).select_related('task_context__task').first()
    if existing and getattr(existing,'task_context',None):
        require_candidate(user,review,existing.target_snapshot)
        if not review_tasks.accessible(user,existing.task_context):raise PermissionDenied
        return existing.task_context.task,False
    if review.status=='COMPLETED':raise ValidationError('먼저 시장 검토를 재개하세요.')
    event=review.decisions.order_by('-pk').first();category={'DOCUMENT':'documents','EVIDENCE':'evidence'}.get(action_type)
    if not event or not category or target_key not in event.targets.get(category,[]):raise ValidationError('시장 판단에 선택한 조치 대상만 업무로 생성할 수 있습니다.')
    candidate=next((r for r in review.snapshot[category] if r['key']==target_key),None)
    if not candidate:raise ValidationError('고정된 조치 대상을 확인하세요.')
    require_candidate(user,review,candidate)
    action,_=MRIChangeAction.objects.get_or_create(review=review,action_type=action_type,target_key=target_key,defaults={'target_snapshot':candidate,'created_by':user})
    return review_tasks.create(user,'PRODUCT_CHANGE',action.pk,**task_values)

def task_source(user,action):
    review=action.review;require_review(user,review);require_candidate(user,review,action.target_snapshot)
    return dict(revision=None,adoption=None,evaluation=None,change_action=action,product=review.change.device,country=review.country,
        identity=['PRODUCT_CHANGE',review.pk,action.action_type,action.target_key],snapshot={'change_id':review.change_id,'review_id':review.pk,'country':review.country,'change_type':review.change.kind,
        'before_value':review.change.before_value,'after_value':review.change.after_value,'action_type':action.action_type,'target':deepcopy(action.target_snapshot)},complaint=None,title=f'제품 변경 {action.get_action_type_display()}: {review.change.device} / {review.country}')
