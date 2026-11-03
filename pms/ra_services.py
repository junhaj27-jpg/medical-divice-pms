"""RA application services; snapshots support review, never legal electronic signatures."""
from datetime import datetime, time, timedelta
import hashlib
import json
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction, models
from django.utils import timezone
from . import ra_models as m
from .models import Attachment, AuditLog, WorkTask, Notification
from .services import role, audit
from .workflow import save_task

REGISTRY={
 'product-versions':(m.ProductRevision,'제품 버전'),
 'changes':(m.ProductChange,'제품 변경·영향 평가'),
 'documents':(m.ControlledDocument,'통제 문서'),
 'labels':(m.LabelVersion,'라벨·사용설명서'),
 'risk-criteria':(m.RiskCriteria,'제품 위험 수용 기준'),
 'product-risks':(m.ProductRisk,'제품 위험관리'),
 'safety-information':(m.SafetyInformation,'외부 안전성 정보'),
 'field-actions':(m.FieldSafetyAction,'현장 안전조치'),
 'field-recipients':(m.FieldActionRecipient,'현장 조치 대상·완료'),
 'suppliers':(m.SupplierRecord,'공급자·제조소·위탁업체'),
 'supplier-materials':(m.SupplierMaterial,'공급자 규제 자료'),
 'training-requirements':(m.TrainingRequirement,'역할별 교육·자격 기준'),
 'training':(m.TrainingAssignment,'교육·수료·재교육'),
 'audit-plans':(m.AuditPlan,'감사·실사 계획'),
 'audit-findings':(m.AuditFinding,'관찰·지적·답변'),
 'audit-packages':(m.AuditPackage,'감사 제출 자료 패키지'),
 'management-reviews':(m.ManagementReview,'정기 검토·경영 보고'),
 'management-decisions':(m.ManagementDecision,'회의 결정·후속 조치'),
 'retention':(m.RetentionPolicy,'조직 보존·파기 정책'),
 'profiles':(m.RegulatoryProfile,'제품 규제 프로필'),
 'requirements':(m.RARequirement,'요구사항 매트릭스'),
 'authorizations':(m.MarketingAuthorization,'인허가·갱신'),
 'packages':(m.SubmissionPackage,'제출 패키지'),
}
SYSTEM_FIELDS={'id','created_by','created_at','updated_at','reviewed_by','reviewed_at','approved_by','approved_at','approval_snapshot','revision','state','frozen_snapshot','management_snapshot','captured_at','automatic_deletion'}
FROZEN={'APPROVED','EFFECTIVE','RETIRED','CANCELLED','CLOSED'}


def require_ra(user):
    if not getattr(user,'is_authenticated',False) or not user.is_active or role(user) not in ('RA_QA','ADMIN'):
        raise PermissionDenied('RA/QA 또는 관리자만 RA 업무 자료를 조회·변경할 수 있습니다.')


def require_admin(user):
    require_ra(user)
    if role(user)!='ADMIN': raise PermissionDenied('관리자 승인이 필요합니다.')


def get_profile(obj):
    if isinstance(obj,m.RetentionPolicy): return obj
    return obj if isinstance(obj,m.RegulatoryProfile) else obj.profile



def locked(obj):
    if isinstance(obj,m.ScopedRecord):
        profile_id=type(obj).objects.values_list('profile_id',flat=True).get(pk=obj.pk) if obj.pk else obj.profile_id
        m.RegulatoryProfile.objects.select_for_update().get(pk=profile_id)
    return type(obj).objects.select_for_update().get(pk=obj.pk) if obj.pk else obj


def digest(data):
    return hashlib.sha256(json.dumps(data,cls=DjangoJSONEncoder,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def snapshot(obj):
    data={f.attname:getattr(obj,f.attname) for f in obj._meta.concrete_fields if f.name not in SYSTEM_FIELDS}
    profile=get_profile(obj)
    data['scope']={'device_id':getattr(profile,'device_id',None),'jurisdiction':getattr(profile,'jurisdiction',None),'organization_id':profile.organization_id,'is_example':profile.is_example}
    for field in obj._meta.concrete_fields:
        if field.is_relation and field.name not in SYSTEM_FIELDS and getattr(obj,field.attname):
            related=getattr(obj,field.name)
            if isinstance(related,Attachment): data[field.name+'_file']={'id':related.pk,'sha256':related.sha256,'scan_status':related.scan_status,'file':str(related.file)}
            elif isinstance(related,m.RARecord):
                related_content={f.attname:getattr(related,f.attname) for f in related._meta.concrete_fields if f.name not in SYSTEM_FIELDS}
                for relation in related._meta.concrete_fields:
                    if relation.is_relation and relation.related_model==Attachment and getattr(related,relation.attname):
                        file=getattr(related,relation.name)
                        related_content[relation.name+'_file']={'sha256':file.sha256,'scan_status':file.scan_status,'file':str(file.file)}
                data[field.name+'_version']={'id':related.pk,'version':getattr(related,'version',None),'approval_hash':related.approval_snapshot.get('hash'),'content_hash':digest(related_content)}
    if isinstance(obj,m.ManagementReview): data['management_snapshot']=obj.management_snapshot
    if obj.pk and isinstance(obj,m.FieldSafetyAction):
        data['planned_targets']=list(obj.recipients.order_by('pk').values('id','partner_id','lot_id','unit','target_quantity'))
    if obj.pk:
        for field in obj._meta.many_to_many:
            rows=getattr(obj,field.name).order_by('pk')
            if field.name=='evidence': data[field.name]=list(rows.values('id','sha256','file','scan_status'))
            elif field.name!='tasks': data[field.name]=list(rows.values_list('pk',flat=True))
    from .ra_operations import approval_context
    if obj.pk: data.update(approval_context(obj))
    return json.loads(json.dumps(data,cls=DjangoJSONEncoder))


def valid_source(obj):
    if not obj.source_url.startswith('https://') or not obj.source_checked_on or not obj.source_checked_by_id:
        raise ValidationError('실제 기준 판단에는 공식 HTTPS 출처·확인일·확인자가 필요합니다. 확인 전에는 확인 필요로 남기세요.')
    if obj.source_checked_on>timezone.localdate(): raise ValidationError('원문 확인일은 미래일 수 없습니다.')


def validate(obj):
    from .ra_operations import validate as validate_operations
    validate_operations(obj)
    profile=get_profile(obj)
    if not obj.owner.is_active or role(obj.owner) not in ('RA_QA','ADMIN'): raise ValidationError('활성 RA/QA 또는 관리자 담당자를 지정하세요.')
    if obj.reviewer_id and (not obj.reviewer.is_active or role(obj.reviewer) not in ('RA_QA','ADMIN')): raise ValidationError('활성 전문 검토자를 지정하세요.')
    if obj.is_example!=profile.is_example: raise ValidationError('실제 자료와 예시 프로필은 연결할 수 없습니다.')
    if isinstance(obj,(m.RegulatoryProfile,m.RARequirement)):
        if obj.applicability!='UNVERIFIED':
            valid_source(obj)
            reason=obj.rationale if isinstance(obj,m.RegulatoryProfile) else obj.applicability_reason
            if not reason.strip(): raise ValidationError('적용·비적용 판단 사유가 필요합니다.')
        if obj.source_id:
            source=obj.source
            if source.device_id and source.device_id!=profile.device_id: raise ValidationError('규정 원문 제품이 일치하지 않습니다.')
            if source.is_example and not obj.is_example: raise ValidationError('예시 원문은 실제 기준에 사용할 수 없습니다.')
    if isinstance(obj,m.RARequirement):
        if obj.clause_id and (not obj.source_id or obj.clause.document_id!=obj.source_id): raise ValidationError('조항과 근거 문서 버전이 일치하지 않습니다.')
        if obj.fulfillment=='NOT_APPLICABLE' and obj.applicability!='NOT_APPLICABLE': raise ValidationError('비적용 판단과 충족 상태를 일치시키세요.')
        if obj.fulfillment=='MET' and (not obj.confirmed_on or not obj.reviewer_id or obj.applicability!='APPLIES'): raise ValidationError('충족 판단에는 적용 근거·검토자·확인일이 필요합니다.')
    if isinstance(obj,m.MarketingAuthorization):
        if obj.status=='APPROVED' and (not obj.number.strip() or not obj.authority.strip() or not obj.verified_on or not obj.verification_source.startswith('https://')):
            raise ValidationError('승인 기록에는 번호·기관·확인일·기관 출처가 필요합니다. 번호만으로 유효성을 보장하지 않습니다.')
    if isinstance(obj,(m.ProductRevision,m.ControlledDocument,m.ProductChange,m.LabelVersion)):
        for name in ('previous','supersedes','from_revision','to_revision','authorization','document','product_revision','change'):
            if getattr(obj,name+'_id',None):
                parent=getattr(obj,name)
                if parent.profile_id!=obj.profile_id or parent.is_example!=obj.is_example: raise ValidationError('연결 제품·국가·조직·예시 범위가 일치하지 않습니다.')
                if parent.pk==obj.pk and type(parent)==type(obj): raise ValidationError('자기 자신을 이전 버전으로 지정할 수 없습니다.')
        if isinstance(obj,m.ControlledDocument):
            if not obj.body.strip() and not obj.primary_file_id: raise ValidationError('통제 문서 본문 또는 원본 파일을 지정하세요.')
            if obj.primary_file_id: validate_evidence(obj,[obj.primary_file])
            if obj.supersedes_id and (obj.supersedes.number!=obj.number or obj.supersedes.version>=obj.version): raise ValidationError('동일 문서번호의 이전 버전을 대체해야 합니다.')
        if isinstance(obj,m.ProductChange):
            if obj.from_revision_id==obj.to_revision_id: raise ValidationError('변경 전후 제품 버전은 달라야 합니다.')
            if obj.submission_decision!='UNVERIFIED' and not obj.decision_basis.strip(): raise ValidationError('제출 필요·불필요 판단 근거가 필요합니다.')
        if isinstance(obj,m.LabelVersion) and obj.udi_id and obj.udi.device_id!=profile.device_id: raise ValidationError('표시 UDI 제품이 일치하지 않습니다.')
    for name in ('product_revision','change','criteria','document','supplier','action','information','notice_document','criteria_document','safety_action','requirement','audit','review'):
        if getattr(obj,name+'_id',None):
            parent=getattr(obj,name)
            if parent.profile_id!=profile.pk or parent.is_example!=obj.is_example: raise ValidationError('연결 기록의 제품·관할·조직·예시 범위가 일치하지 않습니다.')
    for name in ('complaint','capa','recall','report'):
        if getattr(obj,name+'_id',None):
            parent=getattr(obj,name)
            case=parent if name=='complaint' else getattr(parent,'complaint',None)
            device_id=getattr(parent,'device_id',None) if name=='recall' else getattr(case,'device_id',None)
            if device_id!=profile.device_id or (case and case.is_example!=obj.is_example): raise ValidationError('PMS 사건·조치의 제품 또는 예시 구분이 일치하지 않습니다.')
    if getattr(obj,'signal_id',None): validate_domain_links(obj,'signals',[obj.signal])
    if isinstance(obj,m.SafetyInformation):
        if obj.original_id: validate_evidence(obj,[obj.original])
        if obj.relevance!='UNVERIFIED' and not obj.relevance_reason.strip(): raise ValidationError('제품 연관성 판단 사유가 필요합니다.')
        if obj.reporting_decision!='UNVERIFIED' and not obj.reporting_basis.strip(): raise ValidationError('보고 필요성 판단 근거가 필요합니다.')
    if isinstance(obj,m.FieldActionRecipient):
        if obj.action.state in FROZEN:
            if not obj.pk: raise ValidationError('승인된 조치의 대상을 신규 추가할 수 없습니다.')
            old=type(obj).objects.get(pk=obj.pk)
            if any(getattr(old,k)!=getattr(obj,k) for k in ('action_id','partner_id','lot_id','unit','target_quantity')): raise ValidationError('승인된 대상 계획을 변경할 수 없습니다.')
        if obj.completed_quantity and obj.action.state!='EFFECTIVE': raise ValidationError('시행 중 조치에만 완료를 기록하세요.')
        if obj.action.action_type=='RECALL': raise ValidationError('회수 대상·연락·수량은 기존 리콜 원장을 사용하세요.')
        if obj.lot.device_id!=profile.device_id: raise ValidationError('현장 조치 대상 LOT 제품이 일치하지 않습니다.')
        if obj.completed_quantity and (not obj.completed_on or not obj.outcome.strip()): raise ValidationError('완료 수량에는 완료일과 증빙·판단 근거가 필요합니다.')
    if isinstance(obj,m.TrainingAssignment):
        if obj.retraining_of_id and (obj.retraining_of.requirement_id!=obj.requirement_id or obj.retraining_of.trainee_id!=obj.trainee_id or obj.retraining_of.attempt>=obj.attempt): raise ValidationError('같은 대상·교육 기준의 이전 시도를 연결하세요.')
        if obj.attempt>1 and not obj.retraining_of_id: raise ValidationError('재교육에는 이전 시도를 지정하세요.')
        if obj.training_status not in ('INACTIVE','NEEDS_REVIEW') and role(obj.trainee)!=obj.requirement.required_role: raise ValidationError('교육 대상 역할이 일치하지 않습니다. 역할 변경 영향 검토로 남기세요.')
        if not obj.trainee.is_active and obj.training_status!='INACTIVE': raise ValidationError('비활성 대상자는 비활성 교육 상태로 보존하세요.')
        if obj.training_status=='COMPLETED':
            if not obj.completed_on or not obj.completion_evidence_id or obj.effectiveness!='PASS' or not obj.effectiveness_rationale.strip(): raise ValidationError('수료는 수료일·증빙·효과 판정·담당자 근거가 필요합니다. 열람만으로 수료되지 않습니다.')
            if obj.completed_on>timezone.localdate(): raise ValidationError('미래 교육 수료일은 허용하지 않습니다.')
            validate_evidence(obj,[obj.completion_evidence])
    if isinstance(obj,m.RetentionPolicy) and obj.automatic_deletion: raise ValidationError('자동 삭제 기능은 제공하지 않습니다.')
    if isinstance(obj,m.ManagementReview) and obj.period_end>timezone.localdate(): raise ValidationError('집계 종료일은 미래일 수 없습니다.')
    if isinstance(obj,m.ManagementReview) and obj.pms_report_id:
        case=obj.pms_report.complaint
        if case.device_id!=profile.device_id or case.is_example!=obj.is_example: raise ValidationError('PMS 보고서의 제품·예시 구분이 일치하지 않습니다.')
    if isinstance(obj,m.LabelVersion) and obj.previous_id:
        if obj.previous.artifact_type!=obj.artifact_type or obj.previous.language!=obj.language or obj.previous.version>=obj.version: raise ValidationError('동일 언어·자료 유형의 이전 표시 버전을 지정하세요.')
    if isinstance(obj,m.SubmissionPackage):
        if obj.authorization.profile_id!=obj.profile_id: raise ValidationError('허가와 패키지의 규제 프로필이 일치하지 않습니다.')
        if obj.receipt_id: validate_evidence(obj,[obj.receipt])


def validate_evidence(obj,files):
    profile=get_profile(obj)
    for evidence in files:
        if evidence.scan_status!='PASSED': raise ValidationError('검사를 통과한 증빙만 연결하세요.')
        if evidence.ra_profile_id:
            if evidence.ra_profile_id!=profile.pk: raise ValidationError('증빙의 규제 프로필이 일치하지 않습니다.')
        elif evidence.complaint.device_id!=profile.device_id or evidence.complaint.is_example!=obj.is_example:
            raise ValidationError('사건 증빙의 제품·예시 구분이 일치하지 않습니다.')
        from .file_security import safe_attachment_bytes
        safe_attachment_bytes(evidence)


def persist(obj):
    validate(obj)
    obj.full_clean()
    obj._ra_write=True
    try: obj.save()
    finally: obj._ra_write=False


@transaction.atomic
def save_record(obj,user,data,reason,expected_revision=None,links=None):
    require_ra(user)
    if not reason.strip(): raise ValidationError('등록·변경 사유가 필요합니다.')
    model=type(obj)
    if obj.pk:
        obj=locked(obj)
        if expected_revision is None or obj.revision!=int(expected_revision): raise ValidationError('다른 사용자가 변경했습니다. 새로고침 후 검토하세요.')
        if obj.state in FROZEN: raise ValidationError('승인·시행·폐기 기록은 수정할 수 없습니다. 새 버전을 등록하세요.')
        before=snapshot(obj)
    else:
        before={};obj.created_by=user
    from .ra_operations import OPERATION_MODELS
    from . import ra_operations_models as ops
    if model in OPERATION_MODELS:
        forbidden={'baseline','confirmed_trace','components','excerpt','line_number','submission_manifest'}
        if forbidden.intersection(data): raise ValidationError('원문 추출·캡처 필드는 전용 동작으로만 변경하세요.')
    immutable = ()
    if isinstance(obj,ops.ValidationRun):
        immutable=('case','outcome','result','deviation','retest_of')
    elif isinstance(obj,ops.MeetingSource) and obj.pk and ops.MeetingCandidate.objects.filter(meeting=obj).exists():
        immutable=('minutes','project','meeting_on')
    elif isinstance(obj,ops.MeetingCandidate):
        immutable=('meeting',)
    elif isinstance(obj,ops.DHFBaseline) and obj.baseline:
        immutable=('project',)
    elif isinstance(obj,ops.SecurityInventory) and obj.components:
        immutable=('sbom','release')
    if obj.pk:
        for field in immutable:
            if field in data and data[field]!=getattr(obj,field):
                raise ValidationError('실행·원문 이력을 유지하려면 신규 기록을 등록하세요.')
    fields={f.name for f in model._meta.concrete_fields}-SYSTEM_FIELDS
    if set(data)-fields: raise ValidationError('시스템 관리 필드는 직접 지정할 수 없습니다.')
    for name,value in data.items():
        if isinstance(value,m.ControlledDocument) and name not in ('supersedes','previous') and value.state=='RETIRED' and value.pk!=before.get(name+'_id') and not isinstance(obj,(ops.DesignTrace,ops.MeetingCandidate)):
            raise ValidationError('폐기 문서는 신규 근거로 지정할 수 없습니다.')
        setattr(obj,name,value)
    if isinstance(obj,m.TrainingAssignment) and obj.training_status=='COMPLETED' and obj.trainee_id==user.pk: raise ValidationError('본인 교육의 효과 판정은 다른 담당자가 기록해야 합니다.')
    if not obj.pk and 'owner' not in data: obj.owner=user
    profile=get_profile(obj)
    if profile.pk and not isinstance(obj,m.RetentionPolicy): m.RegulatoryProfile.objects.select_for_update().get(pk=profile.pk)
    if not isinstance(obj,(m.RegulatoryProfile,m.RetentionPolicy)) and obj.pk and obj.profile_id!=before.get('profile_id'): raise ValidationError('기존 기록의 제품 규제 프로필은 변경할 수 없습니다.')
    if isinstance(obj,m.RegulatoryProfile) and obj.pk:
        for key in ('device_id','jurisdiction','organization_id','organization_role','is_example'):
            if getattr(obj,key)!=before.get(key): raise ValidationError('기존 프로필의 제품·관할·조직 역할·예시 범위는 변경하지 말고 별도 프로필을 등록하세요.')
    obj.revision+=bool(obj.pk)
    # Editing reviewed material returns it to a draft; previous review is retained in AuditLog.
    if obj.pk and obj.state in ('REVIEW','REVIEWED'):
        obj.state='DRAFT';obj.reviewed_by=None;obj.reviewed_at=None
    persist(obj)
    for field,values in (links or {}).items():
        if field not in {f.name for f in model._meta.many_to_many}: raise ValidationError('알 수 없는 연결입니다.')
        values=list(values)
        if field=='evidence': validate_evidence(obj,values)
        validate_domain_links(obj,field,values)
        if model in OPERATION_MODELS and any(isinstance(value,m.ScopedRecord) and value.profile_id!=obj.profile_id for value in values):
            raise ValidationError('연결 기록은 동일한 규제 프로필이어야 합니다.')
        if field=='lots' and any(lot.device_id!=profile.device_id for lot in values): raise ValidationError('LOT 제품이 일치하지 않습니다.')
        if field=='documents' and any(doc.profile_id!=profile.pk or doc.state!='EFFECTIVE' for doc in values): raise ValidationError('동일 프로필의 시행 문서만 신규 업무에 연결하세요.')
        if field=='tasks' and any(task.ra_profile_id!=profile.pk for task in values): raise ValidationError('업무의 RA 프로필이 일치하지 않습니다.')
        obj._ra_link_write=True
        try: getattr(obj,field).set(values)
        finally: obj._ra_link_write=False
    if isinstance(obj,m.MarketingAuthorization) and before.get('status')!=obj.status:
        m.AuthorizationEvent.objects.create(authorization=obj,status=obj.status,reason=reason,actor=user,snapshot=snapshot(obj))
    audit(user,'RA_SAVE',obj,before,{'data':snapshot(obj),'reason':reason,'revision':obj.revision})
    return obj


@transaction.atomic
def transition(obj,user,action,reason,expected_revision,details=None):
    require_ra(user)
    obj=locked(obj)
    if obj.revision!=int(expected_revision): raise ValidationError('변경된 버전입니다. 다시 검토하세요.')
    if not reason.strip(): raise ValidationError('처리 사유가 필요합니다.')
    old=obj.state
    details=details or {}
    if action=='reopen' and old in ('APPROVED','EFFECTIVE') and isinstance(obj,(m.RegulatoryProfile,m.RARequirement,m.MarketingAuthorization,m.ProductRisk,m.SafetyInformation,m.SupplierRecord,m.SupplierMaterial,m.AuditFinding,m.ManagementDecision)):
        obj.state='DRAFT';obj.reviewed_by=None;obj.reviewed_at=None;obj.approved_by=None;obj.approved_at=None
    elif action=='submit' and old=='DRAFT':
        if not obj.reviewer_id: raise ValidationError('검토자를 지정하세요.')
        obj.state='REVIEW'
    elif action=='review' and old=='REVIEW':
        if obj.reviewer_id!=user.pk and role(user)!='ADMIN': raise PermissionDenied('지정 검토자만 검토할 수 있습니다.')
        obj.state='REVIEWED';obj.reviewed_by=user;obj.reviewed_at=timezone.now()
    elif action=='approve' and old=='REVIEWED':
        require_admin(user)
        if user.pk==obj.created_by_id: raise ValidationError('작성자와 최종 승인자를 분리하세요.')
        if hasattr(obj,'evidence'): validate_evidence(obj,obj.evidence.all())
        check_training_gate(obj,user)
        approval_requirements(obj)
        obj.state='APPROVED';obj.approved_by=user;obj.approved_at=timezone.now()
        content=snapshot(obj)
        obj.approval_snapshot={'schema':1,'revision':obj.revision,'content':content,'hash':digest(content),'reason':reason}
        if isinstance(obj,(m.SubmissionPackage,m.AuditPackage)): obj.frozen_snapshot=content
    elif action=='activate' and old=='APPROVED' and isinstance(obj,(m.ControlledDocument,m.LabelVersion, m.ProductRevision)):
        require_admin(user)
        verify_approval(obj)
        effective=getattr(obj,'effective_on',None)
        if not isinstance(obj,m.ProductRevision) and (not effective or effective>timezone.localdate()): raise ValidationError('시행일을 확인하세요.')
        if isinstance(obj,m.LabelVersion) and obj.document.state!='EFFECTIVE': raise ValidationError('시행 문서 버전만 사용할 수 있습니다.')
        # Serialize competing versions through the existing regulatory profile.
        m.RegulatoryProfile.objects.select_for_update().get(pk=obj.profile_id)
        if isinstance(obj,m.ControlledDocument): previous=m.ControlledDocument.objects.filter(profile=obj.profile,number=obj.number,state='EFFECTIVE')
        elif isinstance(obj,m.LabelVersion): previous=m.LabelVersion.objects.filter(profile=obj.profile,artifact_type=obj.artifact_type,language=obj.language,state='EFFECTIVE')
        else: previous=m.ProductRevision.objects.none()
        if previous.exists(): raise ValidationError('현재 시행본을 사유와 함께 먼저 폐기하세요.')
        obj.state='EFFECTIVE'
    elif action=='retire' and old in ('APPROVED','EFFECTIVE') and isinstance(obj,(m.ControlledDocument,m.LabelVersion,m.ProductRevision)):
        require_admin(user);obj.state='RETIRED'
    elif action=='implement' and old=='APPROVED' and isinstance(obj,m.ProductChange):
        require_admin(user);verify_approval(obj)
        confirmation=details.get('confirmation','').strip()
        if not confirmation: raise ValidationError('실제 시행 확인 근거를 입력하세요.')
        if obj.tasks.exclude(status='DONE').exists(): raise ValidationError('검증·문서·교육 업무를 먼저 완료하세요.')
        obj.state='EFFECTIVE';obj.implemented_on=timezone.localdate();obj.implementation_confirmation=confirmation
    elif action=='activate' and old=='APPROVED' and isinstance(obj,m.FieldSafetyAction):
        require_admin(user);verify_approval(obj)
        if obj.notice_document.state!='EFFECTIVE': raise ValidationError('시행된 승인 안내문이 필요합니다.')
        obj.state='EFFECTIVE'
    elif action=='close' and old=='EFFECTIVE' and isinstance(obj,m.FieldSafetyAction):
        require_admin(user)
        latest=obj.evaluations.order_by('-pk').first()
        if not latest or latest.verdict!='EFFECTIVE' or not obj.closure_rationale.strip(): raise ValidationError('효과 확인과 종결 근거가 필요합니다.')
        if obj.action_type=='RECALL':
            if obj.recall.progress_status!='CLOSED': raise ValidationError('기존 리콜 종결을 먼저 확인하세요.')
        elif obj.recipients.filter(models.Q(completed_quantity__lt=models.F('target_quantity'))|models.Q(acknowledged_on__isnull=True)).exists():
            raise ValidationError('미응답·미조치 대상을 확인하세요.')
        validate_evidence(obj,[latest.evidence])
        if obj.action_type!='RECALL' and not obj.recipients.exists(): raise ValidationError('대상 확인 없이 조치를 종결할 수 없습니다.')
        if obj.tasks.exclude(status='DONE').exists(): raise ValidationError('후속 업무를 먼저 완료하세요.')
        obj.state='CLOSED'
    elif action=='close' and isinstance(obj,m.AuditFinding) and old=='APPROVED':
        require_admin(user);verify_approval(obj)
        if not obj.response.strip() or obj.effectiveness!='PASS' or not obj.effectiveness_rationale.strip(): raise ValidationError('답변·효과 확인·종결 근거가 필요합니다.')
        if obj.capa_id and obj.capa.status!='CLOSED': raise ValidationError('연결 CAPA의 종결을 먼저 확인하세요.')
        obj.state='CLOSED'
    elif action=='close' and isinstance(obj,m.AuditPlan) and old=='APPROVED':
        require_admin(user)
        if obj.findings.exclude(state='CLOSED').exists() or not obj.closure_rationale.strip(): raise ValidationError('지적 종결과 감사 종결 근거가 필요합니다.')
        obj.state='CLOSED'
    elif action=='close' and isinstance(obj,m.ManagementDecision) and old=='APPROVED':
        require_admin(user)
        outcome=details.get('confirmation','').strip()
        if not outcome or obj.tasks.exclude(status='DONE').exists(): raise ValidationError('실제 후속 결과와 업무 완료가 필요합니다.')
        obj.completed_on=timezone.localdate();obj.outcome=outcome
        obj.state='CLOSED'
    elif action=='cancel'  and old in ('DRAFT','REVIEW','REVIEWED','APPROVED'):
        obj.state='CANCELLED'
    else: raise ValidationError('허용되지 않은 RA 처리입니다.')
    obj.revision+=1;persist(obj)
    audit(user,'RA_'+action.upper(),obj,{'state':old},{'state':obj.state,'reason':reason,'revision':obj.revision,'snapshot':obj.approval_snapshot,'data':snapshot(obj)})
    return obj


@transaction.atomic
def schedule_task(obj,user,due_on,title=None):
    require_ra(user)
    obj=locked(obj)
    from .ra_operations_models import MeetingCandidate
    if isinstance(obj,MeetingCandidate) and not obj.confirmed_trace_id:
        raise ValidationError('원문 후보 확인과 DHF 연결을 먼저 완료하세요.')
    if isinstance(obj,m.RetentionPolicy): raise ValidationError('조직 보존 정책에는 자동 업무를 만들지 않습니다.')
    profile=get_profile(obj)
    m.RegulatoryProfile.objects.select_for_update().get(pk=profile.pk)
    if not due_on: raise ValidationError('조직에서 확인한 준비 기한을 지정하세요. 임의 만료일은 만들지 않습니다.')
    if isinstance(obj,m.RetentionPolicy) or obj.state in ('RETIRED','CANCELLED','CLOSED'): raise ValidationError('폐기·종결 기록은 신규 업무에 사용할 수 없습니다.')
    title=title or f'RA 검토: {obj.title}'
    # Idempotent scheduling under parent lock; existing WorkTask/notification service is reused.
    task=(obj.tasks if hasattr(obj,'tasks') else profile.work_tasks).filter(title=title,due_at__date=due_on).first()
    if not task:
        task=WorkTask(ra_profile=profile,assignee=obj.trainee if isinstance(obj,m.TrainingAssignment) else obj.owner,title=title,due_at=timezone.make_aware(datetime.combine(due_on,time(17))))
        save_task(task,user)
        if hasattr(obj,'tasks'):
            obj._ra_link_write=True
            try: obj.tasks.add(task)
            finally: obj._ra_link_write=False
    return task


def approval_requirements(obj):
    from .ra_operations import approval_gate
    approval_gate(obj)
    if isinstance(obj,m.TrainingRequirement) and obj.document.state!='EFFECTIVE': raise ValidationError('시행 문서에 대해 교육을 배정하세요.')
    if isinstance(obj,m.ManagementReview) and not obj.management_snapshot: raise ValidationError('기준일 스냅샷을 먼저 생성하세요.')
    if isinstance(obj,m.ProductRisk):
        if obj.criteria.state not in ('APPROVED','EFFECTIVE'): raise ValidationError('승인된 제품별 위험 수용 기준이 필요합니다.')
        if obj.residual_decision=='UNVERIFIED' or not obj.residual_rationale.strip() or not obj.benefit_risk_rationale.strip(): raise ValidationError('잔여위험·편익 위험에 대한 담당자 판단이 필요합니다.')
        if not obj.verification.strip() or not obj.evidence.exists(): raise ValidationError('위험통제 검증 근거와 증빙이 필요합니다.')
    if isinstance(obj,m.FieldSafetyAction): verify_approval(obj.notice_document)
    if isinstance(obj,m.FieldSafetyAction) and (obj.notice_document.state!='EFFECTIVE' or not obj.effectiveness_criteria.strip()): raise ValidationError('시행 안내문과 효과 확인 기준이 필요합니다.')
    if isinstance(obj,m.SupplierMaterial) and not obj.evidence.exists(): raise ValidationError('공급자 자료 원본 증빙이 필요합니다.')
    if isinstance(obj,m.ProductChange):
        required={'authorization','risk','validation','label','training','pms'}
        if set(obj.impact_checklist)!=required or any(not isinstance(v,str) or not v.strip() for v in obj.impact_checklist.values()):
            raise ValidationError('허가·위험·검증·라벨·교육·PMS 영향 판단과 근거를 모두 기록하세요.')
        if obj.submission_decision=='UNVERIFIED': raise ValidationError('추가 제출 필요 여부를 담당자가 확인해야 시행 승인할 수 있습니다.')
    if isinstance(obj,m.LabelVersion):
        verify_approval(obj.document)
        if not obj.translation_reviewer_id or not obj.translation_reviewed_on or not obj.translation_notes.strip(): raise ValidationError('번역 담당자의 검토 기록이 필요합니다. 자동 번역만으로 승인하지 않습니다.')
        if not obj.translation_reviewer.is_active: raise ValidationError('활성 번역 검토자가 필요합니다.')
        keys={'udi','model','intended_use','warnings','precautions'}
        if set(obj.review_checklist)!=keys or any(v is not True for v in obj.review_checklist.values()): raise ValidationError('표시 검토 항목을 모두 확인하세요.')
        if obj.document.state!='EFFECTIVE': raise ValidationError('현재 시행된 통제 문서 버전을 지정하세요.')


def verify_approval(obj):
    if obj.approval_snapshot.get('schema')!=1 or obj.approval_snapshot.get('hash')!=digest(snapshot(obj)):
        raise ValidationError('승인 당시 버전·증빙이 변경되었습니다. 새 버전으로 검토하세요.')


@transaction.atomic
def revise_document(obj,user,reason):
    require_ra(user)
    obj=locked(obj)
    m.RegulatoryProfile.objects.select_for_update().get(pk=obj.profile_id)
    if obj.state not in FROZEN: raise ValidationError('기존 초안을 편집하세요.')
    data={f.name:getattr(obj,f.name) for f in obj._meta.concrete_fields if f.name not in SYSTEM_FIELDS}
    latest=m.ControlledDocument.objects.filter(profile=obj.profile,number=obj.number).order_by('-version').first()
    data.update(version=latest.version+1,supersedes=obj,change_reason=reason)
    return save_record(m.ControlledDocument(),user,data,reason,links={'evidence':obj.evidence.all()})


def compare_documents(obj):
    if not isinstance(obj,m.ControlledDocument) or not obj.supersedes_id: return {}
    previous=obj.supersedes
    return {field:{'before':getattr(previous,field),'after':getattr(obj,field)} for field in ('title','body','version','change_reason') if getattr(previous,field)!=getattr(obj,field)}


def validate_domain_links(obj,field,values):
    profile=get_profile(obj)
    for parent in values:
        if field in ('complaints','adverse_events','capas'):
            case=parent if field=='complaints' else parent.complaint
            if case.device_id!=profile.device_id or case.is_example!=obj.is_example: raise ValidationError('연결 PMS 자료의 제품·예시 범위가 일치하지 않습니다.')
        if field=='signals':
            group=parent.snapshot.get('group',{})
            if group.get('device_id')!=profile.device_id or parent.snapshot.get('filters',{}).get('example')!=('sample' if obj.is_example else 'real'):
                raise ValidationError('안전 신호의 분석 제품·예시 범위가 일치하지 않습니다.')


@transaction.atomic
def record_field_contact(recipient,user,method,note,evidence=None):
    require_ra(user)
    recipient=locked(recipient)
    if recipient.action.state!='EFFECTIVE': raise ValidationError('시행된 조치의 연락 사실만 기록하세요.')
    if recipient.action.action_type=='RECALL': raise ValidationError('회수 연락은 기존 리콜 연락 원장을 사용하세요.')
    if not method.strip() or not note.strip(): raise ValidationError('연락 방법과 내용을 기록하세요.')
    if evidence: validate_evidence(recipient,[evidence])
    obj=m.FieldActionContact.objects.create(recipient=recipient,actor=user,method=method,note=note,evidence=evidence)
    audit(user,'RA_FIELD_CONTACT',recipient,after={'contact_id':obj.pk,'reason':note})
    return obj


@transaction.atomic
def evaluate_field_action(action,user,verdict,rationale,evidence):
    require_ra(user)
    action=locked(action)
    if action.state!='EFFECTIVE': raise ValidationError('진행 중 조치만 효과를 평가할 수 있습니다.')
    if verdict not in ('EFFECTIVE','INEFFECTIVE') or not rationale.strip(): raise ValidationError('효과 판정과 근거가 필요합니다.')
    validate_evidence(action,[evidence])
    return m.FieldActionEvaluation.objects.create(action=action,actor=user,verdict=verdict,rationale=rationale,evidence=evidence,snapshot=snapshot(action))


def check_training_gate(obj,user):
    if isinstance(obj,(m.RetentionPolicy,m.TrainingRequirement,m.TrainingAssignment)): return
    pending=m.TrainingRequirement.objects.filter(profile=get_profile(obj),state='APPROVED',enforce_ra_approval=True,required_role=role(user))
    for requirement in pending:
        latest=requirement.assignments.filter(trainee=user).order_by('-attempt').first()
        if not latest or latest.training_status!='COMPLETED' or latest.effectiveness!='PASS':
            raise ValidationError('조직이 명시한 RA 승인 사전 교육이 미완료입니다. 기존 PMS 승인 권한은 변경하지 않습니다.')


@transaction.atomic
def sync_training(requirement,user):
    from django.contrib.auth import get_user_model
    require_ra(user)
    requirement=locked(requirement)
    if requirement.state!='APPROVED' or requirement.document.state!='EFFECTIVE': raise ValidationError('승인된 기준과 시행 문서로 대상자를 검토하세요.')
    results=[]
    for person in get_user_model().objects.all().order_by('pk'):
        existing=requirement.assignments.filter(trainee=person).order_by('-attempt').first()
        applies=person.is_active and role(person)==requirement.required_role
        if applies and not existing:
            results.append(save_record(m.TrainingAssignment(),user,dict(profile=requirement.profile,title=f'{requirement.title}: {person.username}',owner=requirement.owner,reviewer=requirement.reviewer,is_example=requirement.is_example,requirement=requirement,trainee=person,due_on=requirement.due_on),'명시적 교육 대상자 검토'))
        elif existing and not applies:
            new='INACTIVE' if not person.is_active else 'NEEDS_REVIEW'
            if existing.training_status!=new:
                existing.training_status=new;existing.revision+=1;persist(existing)
                audit(user,'RA_TRAINING_SCOPE',existing,after={'training_status':new,'reason':'사용자 활성·역할 변경에 따른 명시적 대상 검토'})
    return results


def training_impact(profile):
    results=[]
    for assignment in m.TrainingAssignment.objects.filter(profile=profile).select_related('requirement__document','trainee'):
        document=assignment.requirement.document
        current=m.ControlledDocument.objects.filter(profile=profile,number=document.number,state='EFFECTIVE').first()
        if not assignment.trainee.is_active or role(assignment.trainee)!=assignment.requirement.required_role or (current and current.pk!=document.pk):
            results.append({'assignment_id':assignment.pk,'trainee_id':assignment.trainee_id,'old_document_id':document.pk,'current_document_id':current.pk if current else None,'reason':'활성·역할·문서 버전 영향 검토 필요'})
    return results


@transaction.atomic
def capture_management_review(obj,user,reason,expected_revision):
    from .models import CustomerComplaint,CAPA,RegulatoryReport,Recall,SafetySignal
    require_ra(user)
    obj=locked(obj)
    if obj.state in FROZEN or obj.revision!=int(expected_revision) or not reason.strip(): raise ValidationError('초안의 현재 버전과 캡처 사유가 필요합니다.')
    profile=obj.profile;today=timezone.localdate()
    cases=CustomerComplaint.objects.filter(device_id=profile.device_id,is_example=obj.is_example)
    period=cases.filter(reported_on__range=(obj.period_start,obj.period_end))
    data={'schema':1,'captured_at':timezone.now().isoformat(),'state_basis':'캡처 시점 현재 상태; 과거 시점 상태 복원 아님','period':[str(obj.period_start),str(obj.period_end)],'complaint_report_count':period.count(),'incidence_rate':None,'rate_explanation':'노출량 분모 없음; 보고 건수는 발생률이 아님','reference_links':{'pms':'/analysis/','safety':'/safety/','tasks':'/tasks/'},'current':{}}
    for key,model in [('authorizations',m.MarketingAuthorization),('changes',m.ProductChange),('documents',m.ControlledDocument),('training',m.TrainingAssignment),('supplier_materials',m.SupplierMaterial),('audit_findings',m.AuditFinding),('field_actions',m.FieldSafetyAction),('product_risks',m.ProductRisk)]:
        rows=model.objects.filter(profile=profile).order_by('pk')
        data['current'][key]=[{'id':row.pk,'title':row.title,'state':row.state,'revision':row.revision,'url':f'/ra/{next(k for k,(v,label) in REGISTRY.items() if v==model)}/{row.pk}/','status':getattr(row,'status',getattr(row,'training_status',None)),'due_on':str(getattr(row,'due_on',None) or getattr(row,'next_review_on',None) or ''),'expires_on':str(getattr(row,'expires_on',None) or '')} for row in rows]
    data['current']['pms']={'open_capa_count':CAPA.objects.filter(complaint__in=cases).exclude(status='CLOSED').count(),'report_count':RegulatoryReport.objects.filter(complaint__in=cases).count(),'recall_count':Recall.objects.filter(complaint__in=cases).count(),'safety_signal_ids':[signal.pk for signal in SafetySignal.objects.all() if signal.snapshot.get('group',{}).get('device_id')==profile.device_id and signal.snapshot.get('filters',{}).get('example')==('sample' if obj.is_example else 'real')]}
    previous_end=obj.period_start-timedelta(days=1)
    previous_start=previous_end-(obj.period_end-obj.period_start)
    cohort_signals=SafetySignal.objects.filter(pk__in=data['current']['pms']['safety_signal_ids'])
    def period_counts(start,end):
        return {'complaint_reports':cases.filter(reported_on__range=(start,end)).count(),'new_capas':CAPA.objects.filter(complaint__in=cases,created_at__date__range=(start,end)).count(),'new_safety_signals':sum(start<=timezone.localtime(signal.created_at).date()<=end for signal in cohort_signals)}
    data['count_trends']={'current':period_counts(obj.period_start,obj.period_end),'previous':period_counts(previous_start,previous_end),'previous_period':[str(previous_start),str(previous_end)],'note':'각 기간 신규 건수 비교; 발생률·과거 미해결 상태 아님'}
    data['current']['overdue_task_ids']=list(WorkTask.objects.filter(ra_profile=profile,due_at__lt=timezone.now()).exclude(status='DONE').values_list('pk',flat=True))
    data['unresolved_risks']=obj.unresolved_risks
    obj.management_snapshot=data;obj.captured_at=timezone.now();obj.revision+=1;persist(obj)
    audit(user,'RA_MANAGEMENT_CAPTURE',obj,after={'reason':reason,'snapshot_hash':digest(data),'captured_at':obj.captured_at.isoformat()})
    return obj


@transaction.atomic
def plan_due_reviews(user,as_of=None,horizon_days=30):
    require_ra(user)
    as_of=as_of or timezone.localdate()
    if not 0<=horizon_days<=365: raise ValidationError('조회 범위는 0~365일입니다.')
    planned=[]
    mapping=[(m.RegulatoryProfile,'next_review_on'),(m.RARequirement,'due_on'),(m.RARequirement,'next_review_on'),(m.MarketingAuthorization,'renewal_prepare_on'),(m.ControlledDocument,'next_review_on'),(m.ProductRisk,'next_review_on'),(m.SupplierRecord,'next_review_on'),(m.SupplierMaterial,'next_review_on'),(m.SupplierMaterial,'expires_on'),(m.TrainingAssignment,'due_on'),(m.AuditFinding,'due_on'),(m.ManagementDecision,'due_on')]
    for model,field in mapping:
        for obj in model.objects.exclude(state__in=['RETIRED','CANCELLED','CLOSED']).filter(**{field+'__lte':as_of+timedelta(days=horizon_days)}).order_by('pk'):
            if isinstance(obj,m.TrainingAssignment) and (obj.training_status in ('COMPLETED','INACTIVE') or not obj.trainee.is_active or obj.retraining.exists()): continue
            due=getattr(obj,field)
            label={'due_on':'기한','next_review_on':'정기 검토','renewal_prepare_on':'갱신 준비','expires_on':'유효기간 확인'}[field]
            planned.append(schedule_task(obj,user,due,title=f'RA {label}: {obj.title}'[:200]))
    from .workflow import notify_tasks
    notify_tasks(now=timezone.make_aware(datetime.combine(as_of,time(9))))
    return planned


def available_actions(obj,user):
    actions=[]
    if obj.state=='DRAFT': actions.append(('submit','검토 요청'))
    if obj.state=='REVIEW' and (obj.reviewer_id==user.pk or role(user)=='ADMIN'): actions.append(('review','검토 완료'))
    if obj.state=='REVIEWED' and role(user)=='ADMIN': actions.append(('approve','최종 승인'))
    if obj.state=='APPROVED' and isinstance(obj,(m.ControlledDocument,m.LabelVersion,m.ProductRevision,m.FieldSafetyAction)): actions.append(('activate','시행'))
    if obj.state=='APPROVED' and isinstance(obj,m.ProductChange): actions.append(('implement','변경 시행 확인'))
    if obj.state in ('APPROVED','EFFECTIVE') and isinstance(obj,(m.ControlledDocument,m.LabelVersion,m.ProductRevision)): actions.append(('retire','사유 있는 폐기'))
    if obj.state in ('DRAFT','REVIEW','REVIEWED','APPROVED'): actions.append(('cancel','사유 있는 취소'))
    if obj.state in ('APPROVED','EFFECTIVE') and isinstance(obj,(m.RegulatoryProfile,m.RARequirement,m.MarketingAuthorization,m.ProductRisk,m.SafetyInformation,m.SupplierRecord,m.SupplierMaterial,m.AuditFinding,m.ManagementDecision)): actions.append(('reopen','사유 있는 재검토 개시'))
    if (obj.state=='EFFECTIVE' and isinstance(obj,m.FieldSafetyAction)) or (obj.state=='APPROVED' and isinstance(obj,(m.AuditFinding,m.AuditPlan,m.ManagementDecision))): actions.append(('close','효과·결과 검토 후 종결'))
    return actions


def package_bytes(obj,user):
    import io,zipfile
    from .file_security import safe_attachment_bytes,normalized_name
    require_ra(user)
    if not isinstance(obj,(m.SubmissionPackage,m.AuditPackage)) or obj.state!='APPROVED': raise ValidationError('승인된 패키지만 내려받을 수 있습니다.')
    verify_approval(obj)
    if obj.frozen_snapshot!=obj.approval_snapshot.get('content'): raise ValidationError('제출 스냅샷이 변경되었습니다.')
    files=list(obj.evidence.order_by('pk'))
    if len(files)>100: raise ValidationError('한 패키지는 증빙 100개까지 다운로드할 수 있습니다.')
    stream=io.BytesIO();total=0
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(obj.frozen_snapshot,ensure_ascii=False,indent=2))
        for file in files:
            data=safe_attachment_bytes(file);total+=len(data)
            if total>50*1024*1024: raise ValidationError('패키지 파일 합계는 50MB까지 지원합니다.')
            archive.writestr(f'evidence/{file.pk}-{normalized_name(file.original_name)}',data)
    return stream.getvalue()


from .ra_operations import KINDS
REGISTRY.update(KINDS)
