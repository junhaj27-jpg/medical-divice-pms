"""Registered internal cases only; immutable aggregates, never operational decisions."""
import csv
import io
from collections import Counter
from datetime import date
from uuid import uuid4, UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django import forms
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from .analysis import percentage_change, csv_cell, digest
from .market_models import CaseMarket, COUNTRIES
from .market_service import require_workspace, product_markets, scoped
from .models import MedicalDevice
from .services import visible_complaints, audit
from .period_models import PMSPeriodSnapshot, PMSPeriodComment, PMSPeriodAction

POLICY='internal-case-market-business-date/v1'
SALT='pms-period-preview-v1'

class PeriodForm(forms.Form):
    device=forms.ModelChoiceField(label='제품',queryset=MedicalDevice.objects.none())
    market=forms.ChoiceField(label='판매 시장')
    basis=forms.ChoiceField(label='공통 날짜 기준',choices=[('reported_on','접수일'),('occurred_on','발생일')])
    a_start=forms.DateField(label='기준 A 시작',widget=forms.DateInput(attrs={'type':'date'}))
    a_end=forms.DateField(label='기준 A 종료',widget=forms.DateInput(attrs={'type':'date'}))
    b_start=forms.DateField(label='비교 B 시작',widget=forms.DateInput(attrs={'type':'date'}))
    b_end=forms.DateField(label='비교 B 종료',widget=forms.DateInput(attrs={'type':'date'}))
    example=forms.ChoiceField(label='자료 구분',choices=[('real','운영 자료'),('sample','예시 자료')])
    complaint_type=forms.CharField(label='불만 유형 (정확히 일치, 양쪽 동일)',required=False,max_length=50)
    display_timezone=forms.CharField(label='표시 시간대 (사건 업무상 날짜는 변환하지 않음)',initial='Asia/Seoul',max_length=64)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.user=user
        registrations=product_markets(user).exclude(market='XX')
        self.fields['device'].queryset=MedicalDevice.objects.filter(pk__in=registrations.values('device_id'))
        self.fields['market'].choices=[(m,m) for m in sorted(set(registrations.values_list('market',flat=True)))]
    def clean(self):
        data=super().clean()
        for side in ('a','b'):
            start,end=data.get(side+'_start'),data.get(side+'_end')
            if start and end and (start>end or start.year<1901 or (end-start).days>3660):
                self.add_error(side+'_end','1901년 이후, 양끝 포함 1~3661일을 선택하세요.')
        try:ZoneInfo(data.get('display_timezone',''))
        except (ValueError,ZoneInfoNotFoundError):self.add_error('display_timezone','유효한 IANA 시간대를 입력하세요.')
        if data.get('device') and data.get('market') and not registrations_for(self.user,data['device'].pk,data['market']):
            self.add_error('market','해당 제품에 등록되고 접근 가능한 시장을 선택하세요.')
        return data

# Access checks intentionally use the exact registered product/market pair, even for admins.
def registrations_for(user,device,market):
    return bool(user and product_markets(user).filter(device_id=device,market=market).exists())

def check_scope(user,device,market):
    require_workspace(user)
    if market=='XX' or not registrations_for(user,device,market):raise PermissionDenied

def can_access(user,snapshot):
    try:check_scope(user,snapshot.device_id,snapshot.market)
    except PermissionDenied:return False
    return True

def snapshots_for(user):
    require_workspace(user)
    allowed=product_markets(user).filter(device_id=OuterRef('device_id'),market=OuterRef('market')).exclude(market='XX')
    return PMSPeriodSnapshot.objects.annotate(permitted=Exists(allowed)).filter(permitted=True).select_related('device','actor')

@transaction.atomic
def compare(user, data):
    device=data['device'];check_scope(user,device.pk,data['market'])
    criteria={k:(v.isoformat() if isinstance(v,date) else v) for k,v in data.items() if k!='device'}
    criteria.update(device_id=device.pk,product={'name':device.name,'model':device.model_number},policy=POLICY,unit='unique_complaint_id',boundary='inclusive',date_semantics='business_date_no_timezone_conversion',source='CustomerComplaint + AdverseEvent + CaseMarket')
    basis=data['basis'];start=min(data['a_start'],data['b_start']);end=max(data['a_end'],data['b_end'])
    links=CaseMarket.objects.filter(complaint_id=OuterRef('pk'))
    qs=visible_complaints(user).filter(device=device,is_example=data['example']=='sample')
    if data.get('complaint_type'):qs=qs.filter(complaint_type=data['complaint_type'])
    qs=qs.annotate(in_market=Exists(links.filter(market=data['market'])),any_market=Exists(links.exclude(market='XX')))
    # Scoped accounts cannot inspect unassigned/other-market cases, including their counts.
    qs=qs.filter(in_market=True) if scoped(user) else qs.filter(Q(in_market=True)|Q(any_market=False))
    qs=qs.filter(Q(**{basis+'__range':(start,end)})|Q(**{basis+'__isnull':True}))
    buckets={'a':Counter(),'b':Counter()};excluded={'a':0,'b':0};missing=0;fingerprints=[]
    for row in qs.values('pk','version',basis,'complaint_type','in_market','adverse_event__id','adverse_event__event_type','adverse_event__serious').iterator():
        at=row[basis]
        if at is None:missing+=1;continue
        for side in ('a','b'):
            if not data[side+'_start']<=at<=data[side+'_end']:continue
            if not row['in_market']:excluded[side]+=1;continue
            counts=buckets[side];counts['complaints']+=1;counts['complaint_type:'+row['complaint_type']]+=1
            if row['adverse_event__id']:
                counts['adverse_events']+=1;counts['event_type:'+row['adverse_event__event_type']]+=1
                if row['adverse_event__serious']:counts['serious_adverse_events']+=1
        fingerprints.append(row)
    keys={'complaints','adverse_events','serious_adverse_events'}|set(buckets['a'])|set(buckets['b'])
    rows=[{'metric':key,'a':buckets['a'][key],'b':buckets['b'][key],'delta':buckets['b'][key]-buckets['a'][key],'percent':percentage_change(buckets['a'][key],buckets['b'][key])} for key in sorted(keys)]
    days={s:(data[s+'_end']-data[s+'_start']).days+1 for s in ('a','b')}
    warnings=['불만과 이상사례는 겹치는 집계이며 합산하지 않습니다. 중대성은 입력된 이상사례 플래그입니다.','검증된 제품 사용량 분모가 없어 발생률을 계산하지 않습니다.','외부 CSV와 합산하지 않습니다. 내용 기반 중복 판정은 없으며 사건 ID당 1건입니다.']
    if days['a']!=days['b']:warnings.append('기간 일수가 다릅니다. 원시 건수 비교 시 주의하세요.')
    if max(data['a_start'],data['b_start'])<=min(data['a_end'],data['b_end']):warnings.append('기간이 겹칩니다. 겹친 사건은 양쪽 기간에 각각 1건 집계합니다.')
    if scoped(user):warnings.append('시장 미지정 자료는 접근 권한이 없어 건수를 공개하지 않습니다.')
    if any(excluded.values()):warnings.append('시장 연결이 없는 사건을 제외했습니다. 시장을 추정하지 않습니다.')
    result={'schema_version':1,'rows':rows,'days':days,'quality':{'unassigned_excluded':None if scoped(user) else excluded,'missing_basis_date':missing,'duplicate_links_excluded':0,'duplicate_policy':'exists_market_link; unique_case_id; no_content_deduplication'},'warnings':warnings,'generated_at':timezone.now().isoformat(),'source_digest':digest([{k:str(v) for k,v in r.items()} for r in sorted(fingerprints,key=lambda r:r['pk'])])}
    return criteria,result

def preview_token(user,criteria,result):
    return signing.dumps({'actor':user.pk,'criteria':criteria,'result':result,'request_key':str(uuid4())},salt=SALT,compress=True)

@transaction.atomic
def save_preview(user,token):
    require_workspace(user)
    if not isinstance(token,str) or not token:raise ValidationError('저장할 분석 미리보기를 다시 선택하세요.')
    try:payload=signing.loads(token,salt=SALT,max_age=1800)
    except signing.BadSignature:raise ValidationError('분석 미리보기가 만료되었거나 유효하지 않습니다. 다시 분석하세요.') from None
    if payload['actor']!=user.pk:raise PermissionDenied
    criteria=payload['criteria'];check_scope(user,criteria['device_id'],criteria['market'])
    from .review_tasks import lock
    lock(MedicalDevice,criteria['device_id'])
    snapshot,created=PMSPeriodSnapshot.objects.get_or_create(request_key=UUID(payload['request_key']),defaults={'device_id':criteria['device_id'],'market':criteria['market'],'criteria':criteria,'result':payload['result'],'actor':user})
    if created:audit(user,'PMS_PERIOD_SAVE',snapshot,after={'market':snapshot.market,'policy':POLICY})
    return snapshot

@transaction.atomic
def comment(user,snapshot,note):
    check_scope(user,snapshot.device_id,snapshot.market)
    if not isinstance(note,str) or not note.strip() or len(note)>4000:raise ValidationError('4000자 이내 검토 의견이 필요합니다.')
    record=PMSPeriodComment.objects.create(snapshot=snapshot,actor=user,note=note.strip())
    audit(user,'PMS_PERIOD_COMMENT',snapshot,after={'comment_id':record.pk})
    return record

def task_source(user,action):
    snapshot=action.snapshot;check_scope(user,snapshot.device_id,snapshot.market)
    return dict(revision=None,adoption=None,evaluation=None,analysis_action=action,product=snapshot.device,country=snapshot.market,identity=['PMS_ANALYSIS',snapshot.pk,action.kind],snapshot={'analysis_snapshot_id':snapshot.pk,'kind':action.kind,'criteria':snapshot.criteria,'result':snapshot.result},complaint=None,title=f'PMS {action.get_kind_display()}: {snapshot.criteria["product"]["model"]} #{snapshot.pk}')

@transaction.atomic
def _create_task_atomic(user,snapshot,kind,**values):
    from . import review_tasks
    # Acquire writer/row lock before the first read; unique constraints are the final guard.
    review_tasks.lock(MedicalDevice,snapshot.device_id)
    check_scope(user,snapshot.device_id,snapshot.market)
    if kind not in dict(PMSPeriodAction.KINDS):raise ValidationError('후속 업무 유형을 확인하세요.')
    action,_=PMSPeriodAction.objects.get_or_create(snapshot=snapshot,kind=kind,defaults={'actor':user})
    return review_tasks.create(user,'PMS_ANALYSIS',action.pk,**values)

def create_task(user,snapshot,kind,**values):
    # SQLite shared-cache tests return SQLITE_LOCKED without honoring busy_timeout.
    # Retry the entire rolled-back transaction, never a partially saved task.
    import time
    from django.db import connection, OperationalError
    for attempt in range(6):
        try:return _create_task_atomic(user,snapshot,kind,**values)
        except OperationalError as exc:
            code=getattr(exc.__cause__,'sqlite_errorcode',0) or 0
            if connection.vendor!='sqlite' or connection.in_atomic_block or (code & 255) not in (5,6):raise
            if attempt==5:raise ValidationError('다른 요청이 저장 중입니다. 최신 업무를 확인한 뒤 다시 시도하세요.') from exc
            time.sleep(.05 * 2**attempt)

def export_csv(snapshot):
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['snapshot_id','saved_at','saved_by','product_id','product_name','model','market','example','date_basis','boundary','timezone','date_semantics','unit','policy','a_start','a_end','a_days','b_start','b_end','b_days','metric','a_count','b_count','delta_count','percent_change','quality_json','warnings_json'])
    import json
    c=snapshot.criteria;r=snapshot.result
    for row in r['rows']:
        text=[snapshot.pk,snapshot.created_at.isoformat(),snapshot.actor_id,snapshot.device_id,c['product']['name'],c['product']['model'],snapshot.market,c['example'],c['basis'],c['boundary'],c['display_timezone'],c['date_semantics'],c['unit'],c['policy'],c['a_start'],c['a_end'],r['days']['a'],c['b_start'],c['b_end'],r['days']['b']]
        writer.writerow([csv_cell(v) for v in text]+[csv_cell(row['metric']),row['a'],row['b'],row['delta'],'' if row['percent'] is None else row['percent'],json.dumps(r['quality'],ensure_ascii=False),json.dumps(r['warnings'],ensure_ascii=False)])
    return ('\ufeff'+out.getvalue()).encode('utf-8')
