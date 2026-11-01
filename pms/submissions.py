from .tracking_guard import guarded
"""Manual submission ledger. No network submission or regulator approval inference."""
import hashlib
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import CustomerComplaint, RegulatoryReport, ReportArtifact, SubmissionVersion, SubmissionEvent, Attachment
from .services import visible_complaints, approval_is_current, audit
from .workflow import privileged
from .signal_tracking import identity, replay, evidence
from .approval_integrity import approval_snapshot, digest, row, FIELDS

STATES = {'PREPARED': {'SUBMITTED'}, 'SUBMITTED': {'ACKNOWLEDGED','SUPPLEMENT_REQUESTED','COMPLETED'},
          'ACKNOWLEDGED': {'SUPPLEMENT_REQUESTED','COMPLETED'},
          'SUPPLEMENT_REQUESTED': {'SUPPLEMENT_SUBMITTED'},
          'SUPPLEMENT_SUBMITTED': {'ACKNOWLEDGED','SUPPLEMENT_REQUESTED','COMPLETED'}, 'COMPLETED': set()}


@guarded
@transaction.atomic
def save_submission_plan(user,pk,data):
    privileged(user)
    initial=RegulatoryReport.objects.get(pk=pk,complaint__in=visible_complaints(user))
    CustomerComplaint.objects.select_for_update().get(pk=initial.complaint_id)
    report=RegulatoryReport.objects.select_for_update().get(pk=pk)
    for key in ('submission_authority','submission_channel'):
        value=data.get(key,'')
        if not isinstance(value,str) or not value.strip() or len(value)>200: raise ValidationError('제출 기관·경로를 입력하세요.')
        setattr(report,key,value.strip())
    report.save(update_fields=['submission_authority','submission_channel','updated_at'])
    audit(user,'SUBMISSION_PLAN',report,after={'hash':digest([report.submission_authority,report.submission_channel])})
    return report


def artifact_check(artifact):
    with artifact.file.open('rb') as f:
        if hashlib.sha256(f.read()).hexdigest() != artifact.sha256: raise ValidationError('PDF 내용 해시가 일치하지 않습니다.')
    if artifact.bundle:
        with artifact.bundle.open('rb') as f:
            if hashlib.sha256(f.read()).hexdigest()!=artifact.bundle_sha256: raise ValidationError('증빙 보관본 해시가 일치하지 않습니다.')


@guarded
@transaction.atomic
def prepare_submission(user, pk, data):
    privileged(user)
    report = RegulatoryReport.objects.get(pk=pk,complaint__in=visible_complaints(user))
    case = CustomerComplaint.objects.select_for_update().get(pk=report.complaint_id)
    report = RegulatoryReport.objects.select_for_update().get(pk=pk)
    key, fingerprint = identity(data)
    old = replay(SubmissionVersion,key,fingerprint,report_id=pk,actor_id=user.pk)
    if old: return old
    if not approval_is_current(case): raise ValidationError('제출 준비에는 현행 자료의 유효한 관리자 승인이 필요합니다.')
    if data.get('report_kind') not in ('INITIAL','FOLLOWUP','FINAL'): raise ValidationError('보고 구분을 선택하세요.')
    artifact = ReportArtifact.objects.filter(pk=data.get('artifact'),complaint=case).first()
    current = approval_snapshot(case)['hash']
    if not artifact or artifact.snapshot.get('approval_content_hash') != current: raise ValidationError('승인된 현재 내용으로 PDF를 다시 생성하세요.')
    artifact_check(artifact)
    files = evidence(user,data.get('evidence',[]),[case.pk])
    archived={r['id']:r.get('sha256') for r in artifact.snapshot.get('evidence',[])}
    if files and (not artifact.bundle or any(archived.get(f['id'])!=f['sha256'] for f in files)):
        raise ValidationError('선택 첨부가 포함된 PDF·증빙 보관본을 다시 생성하세요.')
    if not report.submission_authority or not report.submission_channel: raise ValidationError('제출 계획의 기관·경로를 저장하고 재승인하세요.')
    if data.get('authority',report.submission_authority)!=report.submission_authority or data.get('channel',report.submission_channel)!=report.submission_channel: raise ValidationError('승인된 기관·경로와 다릅니다. 제출 계획 변경 후 재승인하세요.')
    snapshot = dict(report=row(report,FIELDS['reports']), approval_hash=current, artifact_id=artifact.pk,
                    pdf_sha256=artifact.sha256, bundle_sha256=artifact.bundle_sha256, artifact_version=artifact.version,
                    attachments=files, authority=report.submission_authority,channel=report.submission_channel)
    content_hash = digest(snapshot)
    same = report.submissions.filter(content_hash=content_hash,report_kind=data['report_kind']).first()
    if same: raise ValidationError('동일 내용의 제출 준비본이 있습니다. 기존 제출본을 사용하세요.')
    version = (report.submissions.order_by('-version').values_list('version',flat=True).first() or 0)+1
    obj = SubmissionVersion.objects.create(report=report,version=version,report_kind=data['report_kind'],artifact=artifact,
          actor=user,request_key=key,request_hash=fingerprint,snapshot=snapshot,content_hash=content_hash)
    audit(user,'SUBMISSION_PREPARE',obj,after={'version':version,'hash':content_hash})
    return obj


@guarded
@transaction.atomic
def record_submission(user, pk, data):
    privileged(user)
    initial = SubmissionVersion.objects.get(pk=pk,report__complaint__in=visible_complaints(user))
    case = CustomerComplaint.objects.select_for_update().get(pk=initial.report.complaint_id)
    obj = SubmissionVersion.objects.select_for_update().select_related('report','artifact').get(pk=pk)
    key, fingerprint = identity(data)
    old = replay(SubmissionEvent,key,fingerprint,submission_id=pk,actor_id=user.pk)
    if old: return old
    last = obj.events.order_by('-pk').first()
    state = last.state if last else 'PREPARED'
    target = data.get('state')
    if target not in STATES[state]: raise ValidationError('허용되지 않은 제출 상태 전이입니다.')
    payload = dict(note=str(data.get('note',''))[:10000])
    if target in ('SUBMITTED','SUPPLEMENT_SUBMITTED'):
        if data.get('confirm') is not True: raise ValidationError('사용자의 명시적 제출 완료 확인이 필요합니다.')
        if not approval_is_current(case): raise ValidationError('내용 변경 시 재승인 후 새 제출본을 준비하세요.')
        submitted = obj
        if target == 'SUPPLEMENT_SUBMITTED':
            submitted = SubmissionVersion.objects.filter(pk=data.get('replacement'),report=obj.report,version__gt=obj.version).first()
            if not submitted: raise ValidationError('보완 제출은 새로운 제출본 버전을 선택하세요.')
            if submitted.events.exists(): raise ValidationError('이미 제출 기록이 있는 버전입니다.')
            payload['replacement'] = submitted.pk
        if submitted.snapshot['approval_hash'] != approval_snapshot(case)['hash']: raise ValidationError('승인 대상 자료가 변경되어 새 제출본이 필요합니다.')
        artifact_check(submitted.artifact)
        for item in submitted.snapshot['attachments']:
            checked = evidence(user,[item['id']],[case.pk])
            if checked != [item]: raise ValidationError('제출 첨부 내용이 변경되었습니다.')
        try: at = parse_datetime(str(data.get('submitted_at','')))
        except ValueError: at=None
        if not at or not timezone.is_aware(at) or at>timezone.now(): raise ValidationError('제출 일시와 시간대를 확인하세요.')
        if not data.get('submitter'): raise ValidationError('실제 제출자를 입력하세요.')
        payload.update(submitted_at=at.isoformat(),submitter=str(data['submitter'])[:200],authority=submitted.snapshot['authority'],channel=submitted.snapshot['channel'])
    if target in ('ACKNOWLEDGED','SUPPLEMENT_REQUESTED'):
        files = evidence(user,data.get('evidence',[]),[case.pk])
        if not files: raise ValidationError('접수 확인서 또는 보완 요청 증빙을 연결하세요.')
        if Attachment.objects.filter(pk__in=[f['id'] for f in files]).exclude(purpose='ADMIN').exists(): raise ValidationError('제출 후 행정 증빙 용도로 등록한 자료를 선택하세요.')
        payload.update(evidence=files,receipt_number=str(data.get('receipt_number',''))[:200])
    if data.get('due_at'):
        # Manual-only deadlines are deliberately supported; no unapproved inference.
        try: due = parse_datetime(str(data['due_at']))
        except ValueError: due=None
        if not due or not timezone.is_aware(due) or not str(data.get('due_reason','')).strip(): raise ValidationError('후속 기한은 시간대와 수동 설정 사유가 필요합니다.')
        payload.update(due_at=due.isoformat(),due_reason=str(data['due_reason'])[:2000],deadline_source='MANUAL')
    event = SubmissionEvent.objects.create(submission=obj,state=target,data=payload,actor=user,request_key=key,request_hash=fingerprint)
    if target=='SUPPLEMENT_SUBMITTED':
        import uuid
        SubmissionEvent.objects.create(submission=submitted,state='SUBMITTED',data=dict(payload,parent_submission=obj.pk),actor=user,request_key=uuid.uuid5(key,'supplement-submitted'),request_hash=fingerprint)
    audit(user,'SUBMISSION_EVENT',event,after={'submission':pk,'state':target})
    return event
