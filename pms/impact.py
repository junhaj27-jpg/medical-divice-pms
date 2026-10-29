"""Saved review candidates do not imply legal applicability or change a case."""
from datetime import datetime, timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import RegulatoryImpact, ImpactReview, WorkTask, Notification, CustomerComplaint, RuleFamilyLock
from .workflow import privileged, save_task
from .services import visible_complaints, audit, role
from .approval_integrity import approval_snapshot, digest
from .regulatory import (rules_for, snapshot_before, matches_case, calculate_deadline,
                         preview_rule, apply_regulated_rule, parse_basis)
from zoneinfo import ZoneInfo


def analyses_for(user):
    if role(user) not in ('RA_QA', 'ADMIN'):
        return RegulatoryImpact.objects.none()
    visible=rules_for(user)
    return RegulatoryImpact.objects.filter(old_rule__in=visible,new_rule__in=visible)


def case_token(case):
    return digest({'approval':approval_snapshot(case)['hash'], 'status':case.status,
                   'version':case.version,'updated_at':case.updated_at})


def rule_token(rule):
    return digest(snapshot_before(rule))


def stale_reason(review, user):
    if not analyses_for(user).filter(pk=review.analysis_id).exists(): raise PermissionDenied
    analysis=review.analysis
    if any(rule_token(r)!=analysis.snapshot[key] for r,key in
           ((analysis.old_rule,'old_token'),(analysis.new_rule,'new_token'))):
        return '분석 이후 규칙이 변경되었습니다. 새 분석을 생성하세요.'
    case=CustomerComplaint.objects.get(pk=review.complaint_id)
    if case_token(case)!=review.snapshot['case_token']:
        return '분석 이후 사건 자료·기한이 변경되었습니다. 새 분석을 생성하세요.'
    return ''


def candidate_preview(rule, case, inputs):
    # A previous date is never promoted to an awareness timestamp or jurisdiction.
    try:
        if not inputs.get('jurisdiction'): raise ValidationError('관할 확인이 필요합니다.')
        if inputs['jurisdiction']!=rule.jurisdiction: raise ValidationError('확인한 관할이 새 규칙과 다릅니다.')
        if not inputs.get('basis_at'): raise ValidationError('명시적인 기준 일시가 필요합니다. 기존 날짜에서 시각을 추정하지 않습니다.')
        if not matches_case(rule,case): raise ValidationError('새 규칙의 제품·조건 범위와 일치하지 않습니다.')
        if rule.is_example and not case.is_example: raise ValidationError('테스트용 규칙은 테스트 사건에만 적용할 수 있습니다.')
        base=parse_basis(inputs['basis_at'],ZoneInfo(rule.timezone_name))
        if rule.basis in ('REPORTED','OCCURRED'):
            expected=case.reported_on if rule.basis=='REPORTED' else case.occurred_on
            if base.date()!=expected: raise ValidationError('기준 일자가 사건 접수일·발생일과 다릅니다.')
        result=calculate_deadline(rule,inputs['basis_at'])
        return {'calculation':result,'error':'','review_only':True}
    except (ValidationError,ValueError,KeyError) as exc:
        return {'calculation':None,'error':' / '.join(exc.messages) if isinstance(exc,ValidationError) else '시간대·조건·입력을 확인하세요.','review_only':True}


@transaction.atomic
def create_analysis(old_rule,new_rule,user,include_closed=False,inputs=None):
    privileged(user)
    scope_lock()
    if not rules_for(user).filter(pk=old_rule.pk).exists() or not rules_for(user).filter(pk=new_rule.pk).exists(): raise PermissionDenied
    old=rules_for(user).select_for_update(of=("self",)).get(pk=old_rule.pk)
    new=rules_for(user).select_for_update(of=("self",)).get(pk=new_rule.pk)
    if old.pk==new.pk: raise ValidationError('서로 다른 두 규칙 버전을 선택하세요.')
    inputs=inputs or {}
    if not isinstance(inputs,dict) or any(not isinstance(v,dict) or set(v)-{'jurisdiction','basis_at'} or any(not isinstance(x,str) for x in v.values()) for v in inputs.values()):
        raise ValidationError('사건번호별 관할·기준 일시 입력을 확인하세요.')
    left=snapshot_before(old);right=snapshot_before(new)
    analysis=RegulatoryImpact.objects.create(old_rule=old,new_rule=new,created_by=user,include_closed=include_closed,
        snapshot={'old':left,'new':right,'old_token':rule_token(old),'new_token':rule_token(new),
                  'changes':{k:{'old':left.get(k),'new':right.get(k)} for k in right if left.get(k)!=right.get(k)}})
    cases=visible_complaints(user)
    if not include_closed: cases=cases.exclude(status='CLOSED')
    for case in cases.select_for_update(of=('self',)).order_by('pk'):
        reasons=[]
        if case.rule_applications.filter(rule=old).exists(): reasons.append('OLD_APPLICATION: 기존 버전 적용 이력')
        if case.status!='CLOSED' and matches_case(new,case): reasons.append('NEW_SCOPE: 새 제품·조건 범위 후보 (관할·시행·실제 적용 별도 확인)')
        if not reasons: continue
        previous=case.rule_applications.order_by('-pk').first()
        provided=inputs.get(str(case.pk),{})
        result=candidate_preview(new,case,provided)
        shortened=bool(previous and result['calculation'] and datetime.fromisoformat(result['calculation']['due_at'])<previous.due_at)
        if not previous and case.due_date and result['calculation']:
            shortened=datetime.fromisoformat(result['calculation']['due_at']).date()<case.due_date
        assignee=case.assignee or user
        if not assignee.is_active or (role(assignee)=='STAFF' and case.reporter_id!=assignee.pk): assignee=user
        task=WorkTask(complaint=case,assignee=assignee,title=f'규정 개정 검토 #{analysis.pk} / CMP-{case.pk}',
                      description='후보 선정은 실제 적용 확정이 아닙니다.',due_at=timezone.now()+timedelta(days=3))
        save_task(task,user)
        review=ImpactReview.objects.create(analysis=analysis,complaint=case,task=task,shortened=shortened,
            snapshot={'reasons':reasons,'case_token':case_token(case),'inputs':provided,'result':result,
                      'previous_id':previous.pk if previous else 0,'previous_rule_id':previous.rule_id if previous else None,
                      'previous_rule_version':previous.rule.version if previous else None,'previous_rule_name':previous.rule.name if previous else None,
                      'previous_snapshot':previous.snapshot if previous else None,
                      'previous_due_at':previous.due_at.isoformat() if previous else None,'previous_due_date':str(case.due_date or '')})
        notify_review(review)
    audit(user,'IMPACT_CREATE',analysis,after={'old_rule':old.pk,'new_rule':new.pk})
    return analysis


def notify_review(review):
    Notification.objects.get_or_create(dedupe_key=f'impact:{review.pk}:{review.task.assignee_id}',
        defaults={'user':review.task.assignee,'title':review.task.title,'message':f'개정 영향 분석 #{review.analysis_id} 검토 업무', 'due_at':review.task.due_at})


def scope_lock():
    import uuid
    key=uuid.UUID(int=0)
    RuleFamilyLock.objects.get_or_create(key=key)
    RuleFamilyLock.objects.filter(pk=key).update(key=key)


@transaction.atomic
def process_review(review,user,status,reason='',assignee=None):
    privileged(user)
    scope_lock()
    review=ImpactReview.objects.select_for_update(of=("self",)).select_related('analysis__old_rule','analysis__new_rule','task').get(pk=review.pk)
    if not analyses_for(user).filter(pk=review.analysis_id).exists(): raise PermissionDenied
    if review.status in ('APPLIED','EXCLUDED'): raise ValidationError('완료 이력은 변경할 수 없습니다. 새 분석을 생성하세요.')
    invalid=stale_reason(review,user)
    if invalid: raise ValidationError(invalid)
    if status not in ('WAITING','IN_PROGRESS','APPLIED','EXCLUDED'): raise ValidationError('검토 상태를 확인하세요.')
    if status in ('APPLIED','EXCLUDED') and not reason.strip(): raise ValidationError('적용·제외 사유는 필수입니다.')
    if status=='APPLIED':
        for rule_id in sorted((review.analysis.old_rule_id,review.analysis.new_rule_id)):
            rules_for(user).select_for_update(of=('self',)).get(pk=rule_id)
        review.analysis.refresh_from_db()
        # Shared application service obtains scope/rule/case locks and rechecks all real-use gates.
        invalid=stale_reason(review,user)
        if invalid: raise ValidationError(invalid)
        data=review.snapshot
        if not data['result']['calculation']: raise ValidationError('계산할 수 없는 후보입니다. 명시적 입력으로 재분석하세요.')
        preview=preview_rule(review.analysis.new_rule,user,data['inputs']['basis_at'])
        if preview.result!=data['result']['calculation']: raise ValidationError('계산이 변경되었습니다. 재분석하세요.')
        app=apply_regulated_rule(review.complaint,review.analysis.new_rule,user,preview,reason,data['previous_id'],data['previous_due_date'],data['case_token'],review.analysis.snapshot['new_token'])
        review.application=app
    task=review.task
    if assignee:
        if not assignee.is_active: raise ValidationError('활성 담당자가 필요합니다.')
        task.assignee=assignee
    task.status='DONE' if status in ('APPLIED','EXCLUDED') else status
    save_task(task,user)
    review.status=status;review.reason=reason
    review.processed_by=user;review.processed_at=timezone.now();review.save()
    notify_review(review)
    audit(user,'IMPACT_REVIEW',review,after={'status':status,'assignee_id':task.assignee_id,'application_id':review.application_id})
    return review
