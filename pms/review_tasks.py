"""Task lifecycle over WorkTask, existing calendars, histories and local notifications."""
import hashlib,json
from copy import deepcopy
from datetime import datetime
from django.db import transaction,connection
from django.core.exceptions import PermissionDenied,ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import WorkTask,TaskHistory,Notification,Attachment,CAPAEvaluation,MedicalDevice,RegulatoryProfile,BusinessPartner
from .review_task_models import ReviewTaskContext,ReviewTaskEvidence
from .market_service import require_workspace,allowed_markets,product_markets,case_markets
from .services import role,audit
from . import dossier
from .dossier_models import RADocumentReview,RADocumentRevision
from .search_models import SearchEvidenceAdoption
from .search_history import adoption_access
from .workflow import save_task,task_state
from .regulatory import rules_for,calculate_deadline,rule_payload


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()

def lock(model,pk):
    if connection.vendor=='sqlite':
        table=connection.ops.quote_name(model._meta.db_table)
        with connection.cursor() as c:c.execute(f'UPDATE {table} SET id=id WHERE id=%s',[pk])
    else:model.objects.select_for_update().get(pk=pk)

def accessible(user,context):
    if not user.is_active or role(user) not in ('RA_QA','ADMIN') or context.country not in allowed_markets(user):return False
    if context.analysis_action_id:
        from .period_analysis import can_access
        return can_access(user,context.analysis_action.snapshot)
    if context.change_action_id:
        from .product_changes import can_review,candidate_access
        return can_review(user,context.change_action.review) and candidate_access(user,context.change_action.review,context.change_action.target_snapshot)
    if context.evaluation_id:return case_markets(user).filter(complaint_id=context.evaluation.capa.complaint_id,market=context.country).exists()
    if not product_markets(user).filter(device_id=context.product_id,market=context.country).exists():return False
    if context.revision_id:return dossier.revision_access(user,context.revision)
    if context.adoption_id:return adoption_access(user,context.adoption)
    return False

def authorized_context_ids(user):
    return [c.task_id for c in ReviewTaskContext.objects.select_related('revision__document__project__device','revision__draft','adoption__draft__project__device','adoption__review__result__run','evaluation__capa','change_action__review__change__device') if accessible(user,c)]

def source(user,kind,pk,country='',section='',source_fingerprint=''):
    require_workspace(user)
    if kind=='PMS_ANALYSIS':
        from .period_models import PMSPeriodAction
        from .period_analysis import task_source
        return task_source(user,PMSPeriodAction.objects.select_related('snapshot__device').get(pk=pk))
    if kind=='PRODUCT_CHANGE':
        from .product_change_models import MRIChangeAction
        from .product_changes import task_source
        action=MRIChangeAction.objects.select_related('review__change__device').get(pk=pk)
        return task_source(user,action)
    if kind=='DOCUMENT':
        event=RADocumentReview.objects.select_related('revision__document__project__device','revision__draft').get(pk=pk)
        revision=event.revision
        if event.state!='REQUESTED' or not dossier.revision_access(user,revision):raise PermissionDenied
        return dict(revision=revision,adoption=None,evaluation=None,product=revision.document.project.device,country=revision.document.country,
            identity=['DOCUMENT',event.pk],snapshot={'review_event_id':event.pk,'revision_id':revision.pk,'document_version':revision.number,'reason':event.reason,'requested_at':event.created_at.isoformat()},complaint=None,title=f'문서 검토: {revision.document.project.device} v{revision.number}')
    if kind in ('IMPACT','ADOPTION_IMPACT'):
        if kind=='IMPACT':
            revision=RADocumentRevision.objects.select_related('document__project__device','draft').get(pk=pk)
            if not dossier.revision_access(user,revision):raise PermissionDenied
            item=next((r for r in dossier.impacts(user,revision) if r['section']==section and r['fingerprint']==source_fingerprint),None)
            adoption=None;product=revision.document.project.device;country=revision.document.country
        else:
            adoption=SearchEvidenceAdoption.objects.select_related('draft__project__device','review__result__run').get(pk=pk)
            if not adoption_access(user,adoption):raise PermissionDenied
            from .source_search import candidates
            item=dossier.change_for(user,adoption.snapshot,candidates(user,include_history=True))
            if not item or item['fingerprint']!=source_fingerprint:item=None
            revision=None
            if adoption.draft_id:
                product=adoption.draft.project.device
                if country not in allowed_markets(user):raise PermissionDenied
            else:
                product=adoption.review.result.entry.complaint.device;country=adoption.review.result.run.market
        if not item:raise ValidationError('현재 변경 조항·버전을 다시 확인하세요.')
        return dict(revision=revision,adoption=adoption,evaluation=None,product=product,country=country,identity=[kind,pk,section,source_fingerprint],snapshot={**item['snapshot'],'section':section,'fingerprint':source_fingerprint},complaint=None,title=f'규정 변경 영향 검토: {product} / {section}')
    if kind=='CAPA':
        evaluation=CAPAEvaluation.objects.select_related('capa__complaint__device').get(pk=pk)
        case=evaluation.capa.complaint
        if not case_markets(user).filter(complaint=case,market=country).exists():raise PermissionDenied
        return dict(revision=None,adoption=None,evaluation=evaluation,product=case.device,country=country,identity=['CAPA',evaluation.pk],snapshot={'evaluation_id':evaluation.pk,'verdict':evaluation.verdict,'criteria':evaluation.criteria,'evaluated_on':str(evaluation.evaluated_on)},complaint=case,title=f'CAPA 효과성 검토·재조치: {evaluation.capa.title}')
    raise ValidationError('업무 원인을 확인하세요.')

def due(user,mode,value,basis,rule_id,country,product):
    now=timezone.now()
    if mode=='MANUAL':
        at=parse_datetime(value) if isinstance(value,str) else value
        if not at or not timezone.is_aware(at):raise ValidationError('수동 기한은 시간대를 포함한 실제 일시로 입력하세요.')
        return at,{'mode':'MANUAL','due_at':at.isoformat(),'selected_at':now.isoformat()}
    if mode!='RULE':raise ValidationError('기한 방식을 확인하세요.')
    rule=rules_for(user).filter(pk=rule_id,state__in=['APPROVED','EFFECTIVE']).first()
    if not rule:raise ValidationError('승인·시행 규칙 버전을 선택하세요.')
    from .market_codes import market_code
    if market_code(rule.jurisdiction)!=country or (rule.device_id and rule.device_id!=product.pk):raise ValidationError('업무 제품·시장에 맞는 규칙을 선택하세요.')
    payload=rule_payload(rule)
    approval=rule.changes.filter(action='RULE_APPROVE',actor_id=rule.approved_by_id).order_by('-pk').first()
    if not approval or any(approval.after.get(k)!=v for k,v in payload.items()):raise ValidationError('규칙 승인 당시 내용과 현재 내용이 다릅니다.')
    if rule.is_example and not product.model_number.startswith('DEMO-'):raise ValidationError('예시 규칙은 예시 제품 업무에만 사용할 수 있습니다.')
    result=calculate_deadline(rule,basis)
    return parse_datetime(result['due_at']),{'mode':'RULE','calculated_at':now.isoformat(),'calculation':result,'rule_snapshot':{'approval_event_id':approval.pk,'approved_payload':payload}}

def ensure_profile(user,product,country):
    profile=RegulatoryProfile.objects.filter(device=product,jurisdiction=country).order_by('pk').first()
    if profile:return profile
    from .ra_services import save_record
    organization,_=BusinessPartner.objects.get_or_create(name=product.manufacturer.name)
    return save_record(RegulatoryProfile(),user,{'device':product,'jurisdiction':country,'organization':organization,'organization_role':'MANUFACTURER','title':f'{country} {product.model_number}','owner':user,'is_example':product.model_number.startswith('DEMO-')},'검토 업무의 제품·시장 범위 등록')

def task_notice(task,kind,token):
    context=task.review_context
    if not accessible(task.assignee,context):return False
    _,created=Notification.objects.get_or_create(dedupe_key=f'review-task:{task.pk}:{task.assignee_id}:{kind}:{token}',defaults={'work_task':task,'user':task.assignee,'title':f'{kind}: {task.title}'[:200],'message':f'업무 #{task.pk} · 관련 근거는 권한 확인 후 업무에서 확인하세요.','due_at':task.due_at})
    return created

def snapshot(task):
    context=task.review_context
    return {**task_state(task),'version':context.version,'cycle':context.cycle,'criteria':context.criteria,'deadline':context.deadline_snapshot,'completed_by':context.completed_by_id,'completed_at':context.completed_at.isoformat() if context.completed_at else None}

@transaction.atomic
def create(user,kind,pk,*,assignee,title,criteria,priority='NORMAL',deadline_mode='MANUAL',due_at='',basis_at='',rule_id=None,country='',section='',source_fingerprint=''):
    origin=source(user,kind,pk,country,section,source_fingerprint)
    lock(MedicalDevice,origin['product'].pk)
    key=digest(origin['identity']);old=ReviewTaskContext.objects.filter(origin_key=key).select_related('task').first()
    if old:
        if not accessible(user,old):raise PermissionDenied
        if old.country!=origin['country']:raise ValidationError('이 원인의 기존 업무 시장을 확인하세요. 기존 업무의 범위는 변경하지 않습니다.')
        return old.task,False
    if kind=='DOCUMENT':
        current=origin['revision'].review_events.order_by('-pk').first()
        latest=origin['revision'].document.revisions.order_by('-number').first()
        if not current or current.pk!=origin['snapshot']['review_event_id'] or latest.pk!=origin['revision'].pk:raise ValidationError('현재 검토 요청이 아닙니다. 최신 문서의 검토 요청을 확인하세요.')
    if not criteria.strip() or len(criteria)>4000 or not title.strip() or len(title)>200:raise ValidationError('업무 제목과 완료 기준을 입력하세요.')
    if priority not in dict(WorkTask._meta.get_field('priority').choices):raise ValidationError('우선순위를 확인하세요.')
    at,calculation=due(user,deadline_mode,due_at,basis_at,rule_id,origin['country'],origin['product'])
    if kind=='CAPA' and origin['evaluation'].followup_id:
        task=origin['evaluation'].followup
        if task.assignee_id!=assignee.pk:raise ValidationError('기존 CAPA 재조치 업무를 열어 담당자를 변경하세요.')
        at=task.due_at;calculation={'mode':'MANUAL','due_at':at.isoformat(),'legacy_followup_preserved':True}
    else:
        task=WorkTask(complaint=origin['complaint'],ra_profile=None if origin['complaint'] else ensure_profile(user,origin['product'],origin['country']),assignee=assignee,title=title,priority=priority,due_at=at,capa=origin['evaluation'].capa if kind=='CAPA' else None)
        task._review_task_history=True;save_task(task,user)
    context=ReviewTaskContext(analysis_action=origin.get('analysis_action'),change_action=origin.get('change_action'),task=task,origin_key=key,origin_kind=kind,product=origin['product'],country=origin['country'],revision=origin['revision'],adoption=origin['adoption'],evaluation=origin['evaluation'],source_snapshot=origin['snapshot'],criteria=criteria,deadline_snapshot=calculation)
    if not accessible(assignee,context):raise ValidationError('담당자에게 제품·시장·원문 접근 권한이 없습니다.')
    if context.revision_id:
        previous=ReviewTaskContext.objects.filter(revision__document_id=context.revision.document_id).order_by('-pk').first()
        if previous:context.parent_task=previous.task
    if context.evaluation_id:
        previous=ReviewTaskContext.objects.filter(evaluation__capa_id=context.evaluation.capa_id).order_by('-pk').first()
        if previous:context.parent_task=previous.task
    context.save()
    TaskHistory.objects.create(task=task,actor=user,before={},after={**snapshot(task),'reason':'원인·대상별 검토 업무 생성'})
    audit(user,'REVIEW_TASK_CREATE',task,after={'kind':kind,'origin_key':key})
    task_notice(task,'ASSIGNED',context.version);task_notice(task,'REVIEW_REQUESTED',context.version)
    return task,True

def files_for(task):
    context=getattr(task,'review_context',None)
    if context and context.change_action_id:
        from django.db.models import Q
        review=context.change_action.review
        from .market_models import EU_COUNTRIES
        scopes=[review.country,'EU' if review.country in EU_COUNTRIES else 'US']
        # Completion proof may be a newly revised document; the request snapshot stays frozen.
        return Attachment.objects.filter(ra_profile__device_id=context.product_id,ra_profile__jurisdiction__in=scopes,scan_status='PASSED')
    if task.complaint_id:return Attachment.objects.filter(complaint_id=task.complaint_id,scan_status='PASSED')
    return Attachment.objects.filter(ra_profile_id=task.ra_profile_id,scan_status='PASSED')

@transaction.atomic
def update(user,task,*,expected,action,reason,comment='',evidence_ids=(),assignee=None,title=None,priority=None,deadline_mode=None,due_at='',basis_at='',rule_id=None,criteria='',criteria_confirmed=False):
    lock(WorkTask,task.pk)
    task=WorkTask.objects.select_related('assignee').get(pk=task.pk);context=ReviewTaskContext.objects.select_related('revision__document__project__device','revision__draft','evaluation__capa','adoption__draft__project__device','adoption__review__result__run').get(task=task)
    if not accessible(user,context):raise PermissionDenied
    task.review_context=context
    if int(expected)!=context.version:raise ValidationError('다른 사용자가 업무를 변경했습니다. 최신 이력과 기한을 확인한 뒤 다시 저장하세요.')
    if not reason.strip() or len(reason)>2000 or len(comment)>4000:raise ValidationError('변경 사유·검토 의견을 확인하세요.')
    before=snapshot(task)
    if action=='edit':
        if task.status=='DONE':raise ValidationError('완료 업무는 재개 후 수정하세요.')
        if criteria:
            if not criteria.strip() or len(criteria)>4000:raise ValidationError('완료 기준을 확인하세요.')
            context.criteria=criteria
        if assignee:task.assignee=assignee
        if title is not None:task.title=title
        if priority is not None:task.priority=priority
        if deadline_mode:task.due_at,context.deadline_snapshot=due(user,deadline_mode,due_at,basis_at,rule_id,context.country,context.product)
    elif action=='reopen':
        if context.change_action_id and context.change_action.review.status=='COMPLETED':raise ValidationError('먼저 제품 변경 시장 검토를 재개하세요.')
        if task.status!='DONE':raise ValidationError('완료 업무만 재개할 수 있습니다.')
        task.status='IN_PROGRESS';context.cycle+=1;context.completed_by=None;context.completed_at=None
    elif action in ('start','request_review','request_changes','complete','evidence'):
        if task.status=='DONE':raise ValidationError('먼저 완료 업무를 재개하세요.')
        if action=='start':task.status='IN_PROGRESS'
        if action=='request_review':task.status='REVIEW'
        if action=='request_changes':task.status='IN_PROGRESS'
        requested=list(dict.fromkeys(int(pk) for pk in evidence_ids))
        files=list(files_for(task).filter(pk__in=requested))
        if len(files)!=len(requested):raise ValidationError('동일 사건·제품 프로필의 검사 통과 증빙만 선택하세요.')
        from .file_security import safe_attachment_bytes
        for file in files:
            safe_attachment_bytes(file)
            ReviewTaskEvidence.objects.get_or_create(task=task,attachment=file,cycle=context.cycle,defaults={'actor':user,'note':comment or reason,'snapshot':{'id':file.pk,'sha256':file.sha256,'file':str(file.file),'name':file.original_name,'cycle':context.cycle}})
        if action=='complete':
            if not criteria_confirmed:raise ValidationError('완료 기준 확인이 필요합니다.')
            if not comment.strip():raise ValidationError('완료 기준을 확인한 검토 의견이 필요합니다.')
            current=list(task.review_evidence.filter(cycle=context.cycle).select_related('attachment'))
            if context.evidence_required and not any(row.snapshot.get('cycle')==context.cycle for row in current):raise ValidationError('이번 수행 회차의 완료 증빙을 연결하세요.')
            for row in current:
                if row.attachment.scan_status!='PASSED' or row.snapshot['sha256']!=row.attachment.sha256:raise ValidationError('완료 증빙 버전·검사 상태를 재확인하세요.')
                safe_attachment_bytes(row.attachment)
            context.completed_by=user;context.completed_at=timezone.now();task.status='DONE'
    else:raise ValidationError('업무 동작을 확인하세요.')
    if not accessible(task.assignee,context):raise ValidationError('담당자의 현재 접근 권한을 확인하세요.')
    context.version+=1;context.save()
    task._review_task_write=True;task._review_task_history=True;save_task(task,user)
    after={**snapshot(task),'reason':reason,'comment':comment,'action':action,'evidence_ids':list(evidence_ids),'criteria_confirmed':criteria_confirmed}
    TaskHistory.objects.create(task=task,actor=user,before=before,after=after);audit(user,'REVIEW_TASK_UPDATE',task,before,after)
    if before['assignee_id']!=task.assignee_id:task_notice(task,'ASSIGNED',context.version)
    if action in ('request_review','request_changes','reopen'):task_notice(task,{'request_review':'REVIEW_REQUESTED','request_changes':'CHANGES_REQUESTED','reopen':'REOPENED'}[action],context.version)
    return task
