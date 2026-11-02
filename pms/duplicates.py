from .tracking_guard import guarded
"""Permission-scoped suspicion and append-only, explicit exclusion decisions."""
from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q
from .models import CustomerComplaint, DuplicateReview
from .services import visible_complaints, role, audit
from .workflow import privileged
from .signal_tracking import identity, replay

FIELDS=('device_id','lot_id','complaint_type','occurred_on','reported_on')
LABELS=('제품','LOT','유형','발생일','접수일')


def candidates(user,case):
    # An empty/null LOT never serves as positive evidence of a shared LOT.
    qs=visible_complaints(user).filter(device_id=case.device_id,is_example=case.is_example).exclude(pk=case.pk)
    match=Q(complaint_type=case.complaint_type)|Q(occurred_on__range=(case.occurred_on-timedelta(days=3),case.occurred_on+timedelta(days=3)))|Q(reported_on__range=(case.reported_on-timedelta(days=3),case.reported_on+timedelta(days=3)))
    if case.lot_id: match |= Q(lot_id=case.lot_id)
    result=[]
    for other in qs.filter(match).order_by('-reported_on','pk')[:100]:
        comparisons=[dict(field=label,current=str(getattr(case,f)),candidate=str(getattr(other,f)),match=getattr(case,f)==getattr(other,f) and getattr(case,f) is not None) for f,label in zip(FIELDS,LABELS)]
        result.append(dict(id=other.pk,url=f'/complaints/{other.pk}/',comparisons=comparisons))
    return result


@guarded
@transaction.atomic
def review_duplicate(user,pk,data):
    privileged(user)
    key,fingerprint=identity(data)
    # Lock cases in stable order, including competing pairs sharing either endpoint.
    try: other_id=int(data.get('other'))
    except (ValueError,TypeError): raise ValidationError('비교 사건을 선택하세요.') from None
    ids=sorted({pk,other_id})
    cases=list(visible_complaints(user).select_for_update().filter(pk__in=ids).order_by('pk'))
    if len(ids)!=2 or len(cases)!=2: raise ValidationError('접근 가능한 별개 사건을 선택하세요.')
    old=replay(DuplicateReview,key,fingerprint,actor_id=user.pk,complaint_id=pk)
    if old: return old
    case=next(c for c in cases if c.pk==pk);other=next(c for c in cases if c.pk==other_id)
    if case.device_id!=other.device_id or case.is_example!=other.is_example: raise ValidationError('동일 제품·예시 구분의 사건만 검토할 수 있습니다.')
    verdict=data.get('verdict');reason=data.get('reason','')
    if verdict not in ('DISTINCT','POSSIBLE','DEFER','EXCLUDE','INCLUDE') or not isinstance(reason,str) or not reason.strip() or len(reason)>10000: raise ValidationError('판단과 근거를 입력하세요.')
    latest=case.duplicate_reviews.order_by('-pk').first()
    if data.get('expected') != (latest.pk if latest else 0): raise ValidationError('검토 이력이 변경되었습니다. 최신 기록을 확인하세요.')
    if verdict in ('EXCLUDE','INCLUDE'):
        if role(user)!='ADMIN': raise PermissionDenied('중복 확정·집계 제외 변경은 관리자만 수행할 수 있습니다.')
        if data.get('confirm') is not True: raise ValidationError('집계 제외 변경의 명시적 확인이 필요합니다.')
        excluded=excluded_ids(user,case.is_example)
        if verdict=='EXCLUDE' and other.pk in excluded: raise ValidationError('대표 사건이 이미 제외되어 있습니다. 대표 사건을 먼저 복원하세요.')
        if verdict=='EXCLUDE':
            # Do not remove a representative while another excluded case points to it.
            for prior in DuplicateReview.objects.filter(other=case,verdict='EXCLUDE'):
                if prior.complaint_id in excluded: raise ValidationError('다른 제외 사건의 대표입니다. 해당 제외를 먼저 해제하세요.')
    record=DuplicateReview.objects.create(complaint=case,other=other,verdict=verdict,reason=reason,actor=user,request_key=key,request_hash=fingerprint)
    audit(user,'DUPLICATE_REVIEW',record,after={'complaint':pk,'other':other_id,'verdict':verdict})
    return record


def excluded_ids(user=None, example=False):
    qs=DuplicateReview.objects.filter(complaint__is_example=example,verdict__in=['EXCLUDE','INCLUDE'])
    if user is not None: qs=qs.filter(complaint__in=visible_complaints(user))
    result=set();seen=set()
    for r in qs.order_by('-pk'):
        if r.complaint_id in seen: continue
        seen.add(r.complaint_id)
        if r.verdict=='EXCLUDE': result.add(r.complaint_id)
    return result
