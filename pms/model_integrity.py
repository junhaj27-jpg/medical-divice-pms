"""Cross-row rules: called inside model save transactions, also usable by preflight."""
from django.core.exceptions import ValidationError


def validate_relations(obj):
    name = obj._meta.object_name
    def fail(message): raise ValidationError(message)
    if name in ('ProductLot', 'CustomerComplaint'):
        if obj.udi_id and obj.device_id and obj.udi.device_id != obj.device_id:
            fail('UDI와 제품이 일치하지 않습니다.')
    if name == 'MedicalDevice' and obj.pk and obj.product_type != 'SOFTWARE' and obj.software_releases.exists():
        fail('릴리스가 있는 제품은 소프트웨어 유형을 유지해야 합니다.')
    if name == 'SoftwareRelease':
        if obj.device_id and obj.device.product_type != 'SOFTWARE':
            fail('소프트웨어 제품에만 릴리스를 등록할 수 있습니다.')
        if obj.pk and type(obj).objects.filter(pk=obj.pk).exclude(
            device_id=obj.device_id, version=obj.version, released_on=obj.released_on
        ).exists():
            fail('등록된 릴리스는 수정할 수 없습니다. 새 버전을 등록하세요.')
    if name == 'CustomerComplaint':
        if obj.intake_release_id and obj.intake_release.device_id != obj.device_id:
            fail('접수 버전은 사건 제품에 속해야 합니다.')
        if obj.pk and type(obj).objects.filter(pk=obj.pk, intake_release__isnull=False).exclude(
            intake_release_id=obj.intake_release_id
        ).exists():
            fail('확인된 접수 버전은 변경할 수 없습니다.')
        if obj.pk and (
            obj.affected_releases.exclude(device_id=obj.device_id).exists()
            or _has_mismatched_verification(obj)
        ):
            fail('영향 버전과 수정 릴리스는 사건 제품에 속해야 합니다.')

        if obj.lot_id and (obj.lot.device_id != obj.device_id or obj.lot.udi_id != obj.udi_id):
            fail('사건의 제품·UDI·LOT가 일치하지 않습니다.')
        if obj.assignee_id and obj.reporter_id:
            validate_assignee(obj.assignee, obj)
        if obj.pk:
            if obj.recalls.exclude(device_id=obj.device_id).exists(): fail('기존 리콜 제품과 일치하지 않습니다.')
            if obj.rule_applications.exclude(rule__device_id=None).exclude(rule__device_id=obj.device_id).exists(): fail('적용 규칙 제품과 일치하지 않습니다.')
            if not obj.is_example and obj.rule_applications.filter(rule__is_example=True).exists(): fail('예시 규칙을 실제 사건에 연결할 수 없습니다.')
    if name == 'AdverseEvent' and obj.patient_id and obj.patient.complaint_id != obj.complaint_id:
        fail('익명 환자는 동일 사건에 속해야 합니다.')
    if name == 'PatientAnonymousInfo' and obj.pk:
        if obj.adverseevent_set.exclude(complaint_id=obj.complaint_id).exists(): fail('연결 이상사례 사건과 일치하지 않습니다.')
    if name in ('RiskAssessment','RegulatoryReport','CAPA') and obj.pk:
        old=type(obj).objects.get(pk=obj.pk)
        if old.complaint_id!=obj.complaint_id: fail('평가·보고·조치의 사건 연결은 변경할 수 없습니다.')
    if name in ('CAPA','Recall') and obj.pk:
        old=type(obj).objects.get(pk=obj.pk)
        if old.complaint_id!=obj.complaint_id and old.tasks.exists(): fail('업무가 연결된 조치의 사건은 변경할 수 없습니다.')
    if name == 'Recall':
        if obj.complaint_id and obj.complaint.device_id != obj.device_id: fail('리콜과 사건의 제품이 일치하지 않습니다.')
        if obj.pk:
            if obj.targets.exclude(lot__device_id=obj.device_id).exists() or obj.recipients.exclude(lot__device_id=obj.device_id).exists(): fail('기존 회수 대상 제품과 일치하지 않습니다.')
            if sum(obj.targets.values_list('target_quantity', flat=True)) > obj.target_quantity: fail('기존 대상 합계보다 목표를 줄일 수 없습니다.')
    if name in ('RecallTarget', 'RecallRecipient') and obj.lot_id and obj.recall_id:
        if obj.lot.device_id != obj.recall.device_id: fail('리콜 제품과 LOT가 일치하지 않습니다.')
        if name == 'RecallTarget':
            total = sum(obj.recall.targets.exclude(pk=obj.pk).values_list('target_quantity', flat=True)) + obj.target_quantity
            if total > obj.recall.target_quantity: fail('대상 합계가 리콜 목표 수량을 초과합니다.')
    if name == 'RecallTarget' and obj.pk:
        old=type(obj).objects.get(pk=obj.pk)
        if old.recall_id!=obj.recall_id: fail('기존 리콜 대상은 다른 리콜로 옮길 수 없습니다.')
    if name == 'RecallRecipient' and obj.pk:
        old=type(obj).objects.get(pk=obj.pk)
        if any(getattr(old,k)!=getattr(obj,k) for k in ('recall_id','lot_id','partner_id','unit','target_quantity','recovered_total')):
            fail('회수 대상 원장·누적 수량은 직접 수정할 수 없습니다.')
    if name == 'ImpactReview':
        if obj.task_id and obj.task.complaint_id!=obj.complaint_id: fail('영향 검토와 업무의 사건이 일치하지 않습니다.')
        if obj.application_id and (obj.application.complaint_id!=obj.complaint_id or obj.application.rule_id!=obj.analysis.new_rule_id): fail('영향 검토의 적용 사건·규칙이 일치하지 않습니다.')
    if name in ('WorkTask','Attachment'):
        if bool(obj.complaint_id)==bool(obj.ra_profile_id): fail('사건 또는 RA 규제 프로필 중 하나만 지정하세요.')
        if obj.pk:
            old=type(obj).objects.get(pk=obj.pk)
            if old.ra_profile_id or obj.ra_profile_id:
                if old.ra_profile_id!=obj.ra_profile_id or old.complaint_id!=obj.complaint_id: fail('RA 업무·증빙의 원래 범위를 변경할 수 없습니다.')
                if name=='Attachment' and (str(old.file)!=str(obj.file) or old.uploaded_by_id!=obj.uploaded_by_id or old.original_name!=obj.original_name): fail('RA 증빙은 새 파일로 등록하고 이전 파일을 보존하세요.')
    if name == 'WorkTask':
        if obj.capa_id and obj.recall_id: fail('CAPA 또는 리콜 중 하나만 연결하세요.')
        for parent in ('capa', 'recall'):
            if getattr(obj, parent + '_id') and getattr(obj, parent).complaint_id != obj.complaint_id: fail('업무와 조치의 사건이 일치하지 않습니다.')
        if obj.assignee_id and obj.complaint_id: validate_assignee(obj.assignee, obj.complaint)
        if obj.assignee_id and not obj.assignee.is_active: fail('활성 담당자가 필요합니다.')
    if name in ('UDI', 'ProductLot') and obj.pk:
        old = type(obj).objects.get(pk=obj.pk)
        keys = ('device_id',) if name == 'UDI' else ('device_id', 'udi_id')
        if any(getattr(old, k) != getattr(obj, k) for k in keys):
            # Product identity is referenced by snapshots and child rows, never silently reparent it.
            fail('기존 UDI·LOT의 제품 연결은 변경할 수 없습니다. 새 항목을 등록하세요.')


def _has_mismatched_verification(complaint):
    from .models import CAPAEvaluation
    return CAPAEvaluation.objects.filter(
        capa__complaint=complaint, fixed_release__isnull=False,
    ).exclude(fixed_release__device_id=complaint.device_id).exists()


def validate_assignee(user, complaint):
    from .services import role
    if not user.is_active: raise ValidationError('활성 담당자만 배정할 수 있습니다.')
    if role(user) == 'STAFF' and user.pk != complaint.reporter_id:
        raise ValidationError('STAFF 담당자는 본인 접수 사건만 배정할 수 있습니다.')
