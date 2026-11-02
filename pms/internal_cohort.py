"""Explicit, minimal internal cohort snapshots. Never updates the source case."""
from django.core.exceptions import ValidationError
from django.db import transaction
from .analysis import require_analyst, digest
from .analysis_models import AnalysisImport, AnalysisRecord, SeriousnessConfirmation
from .models import CustomerComplaint
from .services import visible_complaints, audit
from .approval_integrity import digest as content_digest


def internal_payload(case):
    confirmation = case.seriousness_confirmations.order_by('-pk').first()
    event = getattr(case, 'adverse_event', None)
    # Even a legacy True is only a source flag; explicit confirmation is required.
    payload = dict(case_id=case.pk, version=case.version, device=case.device.name,
                   manufacturer=case.device.manufacturer.name, model=case.device.model_number,
                   occurred_on=str(case.occurred_on), reported_on=str(case.reported_on),
                   event_type=event.event_type if event else case.complaint_type,
                   seriousness=confirmation.value if confirmation else 'UNKNOWN',
                   confirmation_id=confirmation.pk if confirmation else None,
                   is_example=case.is_example,
                   source_content_hash=content_digest(dict(title=case.title,description=case.description,
                       event=dict(type=event.event_type,serious=event.serious,narrative=event.narrative,outcome=event.outcome) if event else None)))
    return payload


def preview_internal(user, ids):
    require_analyst(user)
    if not ids or len(ids)>100: raise ValidationError('1~100개 사건을 선택하세요.')
    cases = list(visible_complaints(user).filter(pk__in=ids).select_related('device__manufacturer').order_by('pk'))
    if len(cases)!=len(set(ids)): raise ValidationError('허용되지 않거나 존재하지 않는 사건입니다.')
    rows=[]
    for case in cases:
        payload=internal_payload(case)
        rows.append(dict(data=payload,hash=digest(payload)))
    return rows


@transaction.atomic
def import_internal(user, expected):
    require_analyst(user)
    ids=sorted(int(k) for k in expected)
    # Source lock shared with ordinary case/adverse-event writes and approvals.
    list(CustomerComplaint.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    rows=preview_internal(user, ids)
    if any(expected[str(r['data']['case_id'])]!=r['hash'] for r in rows):
        raise ValidationError('미리보기 이후 원본이 변경되었습니다. 다시 미리보기 하세요.')
    created=[]
    for r in rows:
        d=r['data']; case_id=d['case_id']
        if AnalysisRecord.objects.filter(source_case_id=case_id,source_hash=r['hash'],origin='INTERNAL').exists(): continue
        previous=AnalysisRecord.objects.filter(source_case_id=case_id,origin='INTERNAL',is_current=True).first()
        if previous:
            previous.is_current=False; previous.save(update_fields=['is_current'])
        batch=AnalysisImport.objects.create(filename=f'internal-CMP-{case_id}',original=b'',sha256=r['hash'],actor=user,is_example=d['is_example'],accepted=1)
        row=AnalysisRecord.objects.create(batch=batch,row_number=1,raw=d,source='INTERNAL',record_id=f'CMP-{case_id}',
            identity=digest(['INTERNAL',case_id,r['hash']]), origin='INTERNAL',source_case_id=case_id,
            source_hash=r['hash'],source_version=d['version'],supersedes=previous,
            device=d['device'],manufacturer=d['manufacturer'],model=d['model'],occurred_on=d['occurred_on'],
            reported_on=d['reported_on'],event_type=d['event_type'],seriousness=d['seriousness'],narrative='')
        created.append(row.pk)
    audit(user,'ANALYSIS_INTERNAL_IMPORT',after={'case_ids':ids,'created_ids':created})
    return created


@transaction.atomic
def confirm_seriousness(user, case_id, value, reason, expected_hash):
    require_analyst(user)
    case=visible_complaints(user).select_for_update(of=('self',)).get(pk=case_id)
    if value not in ('SERIOUS','NON_SERIOUS','UNKNOWN') or not reason.strip() or len(reason)>2000:
        raise ValidationError('중대성 선택과 2000자 이내 확인 사유가 필요합니다.')
    if digest(internal_payload(case))!=expected_hash: raise ValidationError('원본이 변경되었습니다. 다시 확인하세요.')
    # Idempotent repeated confirmation; retain all actual changes as append-only history.
    latest=case.seriousness_confirmations.order_by('-pk').first()
    if latest and latest.value==value and latest.reason==reason.strip() and latest.actor_id==user.pk: return latest
    item=SeriousnessConfirmation.objects.create(complaint=case,value=value,reason=reason.strip(),actor=user)
    audit(user,'SERIOUSNESS_CONFIRM',item,after={'case_id':case.pk,'value':value})
    return item
