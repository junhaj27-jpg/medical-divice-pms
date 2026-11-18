"""Explicit evidence adoption. No rule approval, deadlines or existing draft snapshots are edited."""
from copy import deepcopy
import hashlib,json
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.http import Http404
from .market_service import require_workspace,allowed_markets,scoped,product_markets,eu_access
from .market_codes import market_code
from .market_models import EU_COUNTRIES,MarketComparisonReview
from .regulation_documents import documents_for
from .fda_library_models import FDAReferenceVersion
from .search_models import SourceSearchExecution,SearchEvidenceAdoption,EULegalTextVersion
from .dental_models import DentalDraft
from .services import audit,role

def source_access(user,row):
    require_workspace(user);markets=allowed_markets(user);code=row['jurisdiction']
    if not(code in markets or code=='EU' and set(markets)&set(EU_COUNTRIES)):return False
    if row['kind']=='regulation':
        doc=documents_for(user).filter(pk=row['document_id']).first()
        return bool(doc and (not scoped(user) or not doc.device_id or product_markets(user).filter(device_id=doc.device_id).exists()))
    if row['kind']=='fda':return FDAReferenceVersion.objects.filter(pk=row['source_id']).exists()
    if row['kind']=='eu':return EULegalTextVersion.objects.filter(pk=row['source_id'],document_id=row['document_id']).exists()
    return False

def drafts_for(user):
    require_workspace(user)
    qs=DentalDraft.objects.select_related('project__device')
    if scoped(user):qs=qs.filter(project__device_id__in=product_markets(user).values('device_id'))
    markets=allowed_markets(user)
    types=[]
    if 'US' in markets:types.append('US')
    if set(markets)&set(EU_COUNTRIES):types.append('EU')
    return qs.filter(project__market__in=types)

def draft_access(user,draft):
    from .dental_views import documents_for as controlled_documents
    if not drafts_for(user).filter(pk=draft.pk).exists():return False
    referenced={ref['document_id'] for row in draft.snapshot.get('rows',[]) for ref in row.get('references',[])}
    return referenced.issubset(set(controlled_documents(draft.project.device,draft.project.market).values_list('pk',flat=True)))

def reviews_for(user):
    from .market_review import runs_for
    return MarketComparisonReview.objects.filter(result__run__in=runs_for(user).order_by()).select_related('result__run')

def review_access(user,review):
    from .market_review_views import result_for
    try:result_for(user,review.result_id)
    except (PermissionDenied,Http404):return False
    return reviews_for(user).filter(pk=review.pk).exists()

def record_execution(user,query,filters,result):
    snapshot=deepcopy(result)
    snapshot['results']=[{k:v for k,v in row.items() if k not in ('model_text','parent_hash')} for row in snapshot['results']]
    return SourceSearchExecution.objects.create(actor=user,query_hash=hashlib.sha256(query.encode()).hexdigest(),filters=filters,snapshot=snapshot)

def execution_access(user,event):
    return (role(user)=='ADMIN' or event.actor_id==user.pk) and all(source_access(user,row) for row in event.snapshot['results'])

def adoption_access(user,adoption):
    return source_access(user,adoption.snapshot) and (draft_access(user,adoption.draft) if adoption.draft_id else review_access(user,adoption.review))

@transaction.atomic
def adopt(user,event,key,*,draft=None,review=None,rationale):
    require_workspace(user)
    if not execution_access(user,event):raise PermissionDenied
    if bool(draft)==bool(review):raise ValidationError('초안 또는 검토 기록 중 하나를 선택하세요.')
    if draft and not draft_access(user,draft) or review and not review_access(user,review):raise PermissionDenied
    row=next((r for r in event.snapshot['results'] if r['key']==key),None)
    if not row or not source_access(user,row):raise PermissionDenied
    target_market=draft.project.market if draft else review.result.run.market
    source_market=row['jurisdiction']
    if not(source_market==target_market or source_market=='EU' and target_market in (*EU_COUNTRIES,'EU')):
        raise ValidationError('근거의 관할과 연결 대상 시장이 다릅니다.')
    if not rationale.strip() or len(rationale)>2000:raise ValidationError('채택 사유를 입력하세요.')
    identifier=f'{user.pk}|{event.pk}|{key}|{draft.pk if draft else ""}|{review.pk if review else ""}|{rationale}'
    snapshot=deepcopy(row)
    snapshot.update(search_engine=event.snapshot['engine'],model_id=event.snapshot['model_id'],model_revision=event.snapshot['revision'],adopted_excerpt=row['text'])
    obj,created=SearchEvidenceAdoption.objects.get_or_create(dedupe_key=hashlib.sha256(identifier.encode()).hexdigest(),defaults={
        'actor':user,'execution':event,'draft':draft,'review':review,'snapshot':snapshot,'rationale':rationale})
    if created:audit(user,'SOURCE_EVIDENCE_ADOPT',obj,after={'execution_id':event.pk,'draft_id':draft.pk if draft else None,'review_id':review.pk if review else None})
    return obj,created
