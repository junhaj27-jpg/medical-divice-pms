from .tracking_guard import guarded
"""Internal product review snapshots; never claims statutory PSUR/PMS compliance."""
import json
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import (MedicalDevice, CAPA, Recall, WorkTask, RegulatoryReport,
    PMSPeriodicReport, AnalysisRecord, DuplicateReview)
from .workflow import privileged, recall_totals
from .services import visible_complaints, audit
from .safety import signals_for
from .approval_integrity import digest
from .signal_tracking import identity, replay, day
from .internal_cohort import internal_payload


from .duplicates import excluded_ids


def build_snapshot(user, device, start, end, example):
    length=(end-start).days+1; previous_start=start-timedelta(days=length); previous_end=start-timedelta(days=1)
    base=visible_complaints(user).filter(device=device,is_example=example)
    excluded=excluded_ids(user,example)
    rows=[]
    def metric(label, objects, kind, detail=None, count_unit='건', inclusion=''):
        objects=list(objects)
        paths={'case':'/complaints/{}/','capa':'/capas/{}/','recall':'/recalls/{}/ledger/',
               'task':'/tasks/{}/','signal':'/safety/signals/{}/tracking/','report':'/reports/{}/tracking/',
               'analysis':'/analysis/imports/{}/'}
        refs=[]
        for o in objects:
            ident=o.batch_id if kind=='analysis' else o.pk
            refs.append(dict(id=o.pk,url=paths[kind].format(ident),label=f'{kind} #{o.pk}',detail=detail(o) if detail else {f:str(getattr(o,f)) for f in ('device_id','lot_id','complaint_type','occurred_on','reported_on')} if kind=='case' else ''))
        rows.append(dict(label=label,count=len(objects),count_unit=count_unit,inclusion=inclusion,evidence=refs))
    current=list(base.filter(occurred_on__range=(start,end)).exclude(pk__in=excluded).order_by('pk'))
    previous=list(base.filter(occurred_on__range=(previous_start,previous_end)).exclude(pk__in=excluded).order_by('pk'))
    metric('내부 사건 / 기간 내 발생 불만',current,'case')
    metric('내부 사건 / 동일 길이 직전 기간 발생 불만',previous,'case')
    metric('내부 사건 / 기간 내 발생 이상사례', [c for c in current if hasattr(c,'adverse_event')],'case')
    metric('내부 사건 / 중대성 확인 미상', [c for c in current if internal_payload(c)['seriousness']=='UNKNOWN'],'case')
    metric('내부 사건 / 중대성 확인 중대', [c for c in current if internal_payload(c)['seriousness']=='SERIOUS'],'case')
    metric('내부 사건 / 중복 확정으로 향후 집계 제외',base.filter(occurred_on__range=(start,end),pk__in=excluded),'case')
    external=AnalysisRecord.objects.filter(batch__is_example=example,is_current=True,origin='CSV',
        manufacturer=device.manufacturer.name,device=device.name,model=device.model_number)
    metric('CSV 별도 코호트 / 기간 내 발생 (내부 사건과 합산하지 않음)',external.filter(occurred_on__range=(start,end)),'analysis')
    metric('CSV 별도 코호트 / 직전 기간 발생',external.filter(occurred_on__range=(previous_start,previous_end)),'analysis')
    metric('CSV 별도 코호트 / 기간 내 중대성 미상',external.filter(occurred_on__range=(start,end),seriousness='UNKNOWN'),'analysis')
    metric('CSV 별도 코호트 / 발생일 누락으로 기간 통계 제외',external.filter(occurred_on__isnull=True),'analysis')
    internal=AnalysisRecord.objects.filter(source_case__in=base,batch__is_example=example,
        origin='INTERNAL',occurred_on__range=(start,end))
    metric('내부 가져오기 코호트 / 기간 내 (원본 사건과 중복 합산하지 않음)',
        internal.filter(is_current=True).exclude(source_case_id__in=excluded),'analysis',count_unit='스냅샷',
        inclusion='활성 집계: 최신 내부 버전만 포함하며 원본 사건의 ADMIN 집계 제외를 적용합니다. 내부 사건 건수와 합산하지 않습니다.')
    metric('보존 스냅샷 / 내부 가져오기 전체 버전 수',internal,'analysis',count_unit='스냅샷',
        inclusion='보관 현황: 집계 제외 사건과 정정 전 버전도 포함합니다. 사건 발생 건수가 아니며 활성 집계와 합산하지 않습니다.')
    signals=[]
    for signal in signals_for(user):
        if signal.snapshot.get('group',{}).get('device_id')==device.pk and bool(signal.snapshot.get('filters',{}).get('example')=='sample')==example:
            signals.append(signal)
    metric('기준일 현재 / 안전 신호 및 조사·조치',signals,'signal',lambda s:dict(status=s.status,tracking=list(s.tracking.values('kind','data','created_at'))))
    metric('기준일 현재 / CAPA 효과성 평가',CAPA.objects.filter(complaint__in=base),'capa',lambda c:dict(status=c.status,evaluations=list(c.evaluations.values('id','evaluated_on','verdict','rationale'))))
    metric('기준일 현재 / 미완료 업무',WorkTask.objects.filter(complaint__in=base).exclude(status='DONE'),'task',lambda t:dict(status=t.status,due_at=t.due_at))
    metric('기준일 현재 / 리콜 대상·회수·미회수',Recall.objects.filter(complaint__in=base),'recall',lambda r:dict(status=r.progress_status,ledger=recall_totals(r),legacy_target=r.target_quantity,legacy_recovered=r.recovered_quantity,legacy_note='기존 수기 집계 · 원장과 합산하지 않음',recipients=list(r.recipients.values('id','unit','target_quantity','recovered_total','unrecovered_reason'))))
    metric('기준일 현재 / 규제보고 제출·보완',RegulatoryReport.objects.filter(complaint__in=base),'report',lambda r:dict(versions=[dict(id=v.pk,version=v.version,kind=v.report_kind,events=list(v.events.values('state','created_at','data'))) for v in r.submissions.all()]))
    result=dict(title='내부 PMS 정기 검토 보고서',device=dict(id=device.pk,name=device.name,model=device.model_number,manufacturer=device.manufacturer.name,udis=list(device.udis.values_list('device_identifier',flat=True))),
        start=start,end=end,previous_start=previous_start,previous_end=previous_end,is_example=example,as_of=timezone.now(),metrics=rows,
        limits=['발생 건수는 occurred_on 기준이며 접수일 통계와 다릅니다.','업무 상태는 생성 시점 현재 상태입니다. 기간 말 과거 상태를 복원하지 않았습니다.',
        'CSV와 내부 사건은 출처별 별도 표시하며 합산하지 않습니다. CSV의 제품 매핑은 제조사·제품명·모델의 정확한 문자열 일치 기준입니다.',
        '중대성 확인이 없는 내부 사건은 미상으로 처리합니다. CSV 중복 거부 이력은 원본 가져오기 목록에서 확인합니다.',
        '단순 중복 의심은 제외하지 않습니다. ADMIN 확정 제외만 새 보고서에 적용하며 기존 보고서·신호 근거는 변경하지 않습니다.',
        '내부 가져오기 활성 집계에는 원본 사건의 집계 제외를 적용합니다. 전체 보존 스냅샷 수는 제외 사건·정정 전 버전도 포함하는 보관 현황이며 사건 건수가 아닙니다.',
        '분모·노출량이 없어 발생률이나 인과관계를 확정하지 않습니다. 법정 PSUR/PMS 보고서 적합성을 자동 보장하지 않습니다.'])
    return json.loads(json.dumps(result,default=str,ensure_ascii=False))


@guarded
@transaction.atomic
def create_periodic(user,data):
    privileged(user)
    key,fingerprint=identity(data)
    old=replay(PMSPeriodicReport,key,fingerprint,actor_id=user.pk)
    if old: return old
    device=MedicalDevice.objects.select_for_update().get(pk=data.get('device'))
    start,end=day(data.get('start')),day(data.get('end'))
    if start>end or (end-start).days>3660: raise ValidationError('검토 기간을 확인하세요 (최대 10년).')
    if not isinstance(data.get('is_example',False),bool): raise ValidationError('예시 구분은 참/거짓이어야 합니다.')
    example=data.get('is_example',False)
    qs=PMSPeriodicReport.objects.filter(device=device,start=start,end=end,is_example=example)
    version=(qs.order_by('-version').values_list('version',flat=True).first() or 0)+1
    snapshot=build_snapshot(user,device,start,end,example);snapshot['author_id']=user.pk
    obj=PMSPeriodicReport.objects.create(device=device,start=start,end=end,is_example=example,version=version,
         snapshot=snapshot,content_hash=digest(snapshot),actor=user,request_key=key,request_hash=fingerprint,review_note='')
    audit(user,'PMS_PERIOD_DRAFT',obj,after={'version':version,'hash':obj.content_hash})
    return obj


@guarded
@transaction.atomic
def finalize_periodic(user,pk,data):
    privileged(user)
    source=PMSPeriodicReport.objects.get(pk=pk)
    MedicalDevice.objects.select_for_update().get(pk=source.device_id)
    key,fingerprint=identity(dict(data,source=pk))
    old=replay(PMSPeriodicReport,key,fingerprint,actor_id=user.pk,source_id=pk)
    if old: return old
    if source.stage!='DRAFT' or PMSPeriodicReport.objects.filter(source=source,stage='FINAL').exists(): raise ValidationError('이미 확정된 초안입니다. 새 버전을 작성하세요.')
    if data.get('confirm') is not True or not str(data.get('review_note','')).strip(): raise ValidationError('검토 의견과 명시적 확정이 필요합니다.')
    if digest(source.snapshot)!=source.content_hash: raise ValidationError('초안 스냅샷 무결성 오류입니다.')
    latest=PMSPeriodicReport.objects.filter(device=source.device,start=source.start,end=source.end,is_example=source.is_example).order_by('-version').first()
    obj=PMSPeriodicReport.objects.create(device=source.device,start=source.start,end=source.end,is_example=source.is_example,version=latest.version+1,
        stage='FINAL',source=source,snapshot=source.snapshot,content_hash=source.content_hash,actor=user,reviewer=user,review_note=data['review_note'],request_key=key,request_hash=fingerprint)
    audit(user,'PMS_PERIOD_FINAL',obj,after={'version':obj.version,'source':pk,'hash':obj.content_hash})
    return obj
