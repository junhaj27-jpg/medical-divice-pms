from .tracking_guard import guarded
import uuid
from datetime import date, datetime, time
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import CustomerComplaint, CAPA, Recall, CAPAEvaluation, Attachment, SignalTracking
from .services import visible_complaints, audit
from .workflow import privileged
from .safety import signals_for, review_signal
from .approval_integrity import digest


def identity(data):
    try: key = uuid.UUID(str(data.get('request_key')))
    except (ValueError, TypeError): raise ValidationError('요청 UUID가 필요합니다.') from None
    return key, digest({k:v for k,v in data.items() if k != 'request_key'})


def replay(model, key, fingerprint, **scope):
    old = model.objects.filter(request_key=key).first()
    if old and (old.request_hash != fingerprint or any(getattr(old,k) != v for k,v in scope.items())):
        raise ValidationError('요청 키를 다른 내용에 재사용할 수 없습니다.')
    return old


def day(value):
    try: return date.fromisoformat(str(value))
    except (ValueError, TypeError): raise ValidationError('올바른 날짜를 입력하세요.') from None


def evidence(user, ids, case_ids):
    if not isinstance(ids, list): raise ValidationError('증빙 ID 목록을 입력하세요.')
    files = list(Attachment.objects.filter(pk__in=ids, complaint_id__in=case_ids,
                 complaint__in=visible_complaints(user), scan_status='PASSED'))
    if len(files) != len(set(ids)): raise ValidationError('접근 가능한 동일 사건의 검사 통과 증빙만 허용됩니다.')
    from .file_security import safe_attachment_bytes
    for f in files: safe_attachment_bytes(f)
    return [dict(id=f.pk, sha256=f.sha256) for f in files]


def linked_actions(signal):
    cap, rec = set(), set()
    for h in signal.history.all():
        if h.links.get('capa'): cap.add(h.links['capa'])
        if h.links.get('recall'): rec.add(h.links['recall'])
    for h in signal.tracking.all():
        if h.capa_id: cap.add(h.capa_id)
        if h.recall_id: rec.add(h.recall_id)
    return CAPA.objects.filter(pk__in=cap), Recall.objects.filter(pk__in=rec)


def closure_check(signal):
    capas, recalls = linked_actions(signal)
    evidence_ids={c['pk'] for c in signal.snapshot['evidence']}
    device_id=signal.snapshot['group']['device_id']
    if capas.exclude(complaint_id__in=evidence_ids,complaint__device_id=device_id).exists() or recalls.exclude(complaint_id__in=evidence_ids,complaint__device_id=device_id,device_id=device_id).exists():
        raise ValidationError('신호·조치·사건의 제품 또는 연결 범위가 변경되었습니다. 재검토하세요.')
    if capas.exclude(status='CLOSED').exists() or recalls.exclude(progress_status__in=['COMPLETED','CLOSED']).exists():
        raise ValidationError('미완료 연결 조치가 있어 신호를 종결할 수 없습니다.')
    for c in capas:
        latest = c.evaluations.order_by('-pk').first()
        if not latest or latest.verdict != 'PASS' or not latest.evidence.exists(): raise ValidationError('연결 CAPA의 증빙을 포함한 적합 효과성 평가가 필요합니다.')
    latest_effect = signal.tracking.filter(kind='EFFECT').order_by('-pk').first()
    if recalls.exists() and (not latest_effect or latest_effect.data.get('verdict') != 'PASS' or not set(recalls.values_list('pk',flat=True)).issubset(set(latest_effect.data.get('recall_ids',[])))):
        raise ValidationError('리콜 조치의 효과 확인일·결과·증빙을 먼저 기록하세요.')
    decision = signal.tracking.exclude(kind='CLOSE').order_by('-pk').first()
    if not capas.exists() and not recalls.exists() and (not decision or decision.kind != 'NO_ACTION'):
        raise ValidationError('최신 조사·재검토 이후 조치 불필요 사유 검토가 필요합니다.')
    if decision and decision.kind in ('HOLD', 'ACTION_REQUIRED', 'REOPEN'):
        raise ValidationError('판단 보류·조치 필요·재검토 상태에서는 종결할 수 없습니다.')


@guarded
@transaction.atomic
def track_signal(user, pk, data):
    privileged(user)
    initial = signals_for(user).get(pk=pk)
    ids = sorted(c['pk'] for c in initial.snapshot['evidence'])
    cases = list(visible_complaints(user).select_for_update().filter(pk__in=ids).order_by('pk'))
    if len(cases) != len(ids): raise ValidationError('신호 근거 사건에 대한 접근 권한을 확인하세요.')
    signal = signals_for(user).select_for_update(of=('self',)).get(pk=pk)
    key, fingerprint = identity(data)
    old = replay(SignalTracking, key, fingerprint, signal_id=pk, actor_id=user.pk)
    if old: return old
    kind = data.get('kind')
    allowed = {'INVESTIGATE','NO_ACTION','ACTION_REQUIRED','HOLD','LINK','DRAFT_CAPA','DRAFT_RECALL','CLOSE','REOPEN','EFFECT'}
    if kind not in allowed: raise ValidationError('허용되지 않은 작업입니다.')
    if signal.status == 'CLOSED' and kind not in ('REOPEN','EFFECT'): raise ValidationError('종결 신호는 재검토로 전환하세요.')
    note = data.get('note','')
    if not isinstance(note,str) or not note.strip() or len(note)>10000: raise ValidationError('확인 내용·사유가 필요합니다.')
    payload = dict(note=note)
    capa = recall = evaluation = None
    status = 'REVIEW'
    assignee = data.get('assignee', signal.assignee_id)
    payload['assignee_id']=int(assignee)
    if kind == 'INVESTIGATE':
        if not data.get('basis'): raise ValidationError('조사 근거가 필요합니다.')
        payload.update(basis=str(data['basis'])[:10000], due_on=day(data.get('due_on')).isoformat(),
                       evidence=evidence(user,data.get('evidence',[]),ids))
    if kind == 'NO_ACTION':
        if signal.status != 'REVIEW': raise ValidationError('조사 검토 중에만 조치 불필요 판단을 기록할 수 있습니다.')
        if any(q.exists() for q in linked_actions(signal)): raise ValidationError('연결 조치가 있어 조치 불필요로 처리할 수 없습니다.')
    if kind in ('LINK','DRAFT_CAPA','DRAFT_RECALL'):
        if kind.startswith('DRAFT_'):
            if data.get('confirm') is not True: raise ValidationError('신규 초안 생성의 명시적 요청이 필요합니다.')
            case = next((c for c in cases if c.pk == data.get('complaint')),None)
            if not case: raise ValidationError('신호 근거 사건을 선택하세요.')
            due = day(data.get('due_on'))
            # The locked signal plus natural action identity handles retries with a fresh key too.
            existing = signal.tracking.filter(kind=kind, data__complaint=case.pk).first()
            if existing: raise ValidationError('이 신호·사건의 조치 초안이 이미 있습니다. 기존 조치를 연결하세요.')
            payload['complaint'] = case.pk
            if kind == 'DRAFT_CAPA':
                capa = CAPA.objects.create(complaint=case,title=f'안전 신호 #{pk} 조사 초안',corrective_action='검토 후 조치 계획 확정 필요',owner=user,due_date=due)
            else:
                qty = case.lot.distributed_quantity if case.lot_id else 0
                recall = Recall.objects.create(complaint=case,device=case.device,title=f'안전 신호 #{pk} 리콜 검토 초안',reason=note,risk_level='UNKNOWN',distributed_quantity=qty,target_quantity=0,start_date=timezone.localdate(),expected_end_date=due,owner=user)
        else:
            if bool(data.get('capa')) == bool(data.get('recall')): raise ValidationError('하나의 기존 조치를 선택하세요.')
            capa = CAPA.objects.filter(pk=data.get('capa'),complaint_id__in=ids).first() if data.get('capa') else None
            recall = Recall.objects.filter(pk=data.get('recall'),complaint_id__in=ids).first() if data.get('recall') else None
            if not capa and not recall: raise ValidationError('신호 근거 사건의 조치만 연결할 수 있습니다.')
        obj = capa or recall
        case = next(c for c in cases if c.pk == obj.complaint_id)
        group = signal.snapshot['group']
        if case.device_id != group['device_id'] or (recall and recall.device_id != case.device_id):
            raise ValidationError('신호·사건·조치 제품이 일치하지 않습니다.')
        status = 'ACTION'
    if kind == 'EFFECT':
        capas, recalls = linked_actions(signal)
        if capas.exclude(status='CLOSED').exists() or recalls.exclude(progress_status__in=['COMPLETED','CLOSED']).exists():
            raise ValidationError('조치 완료 후 효과를 확인하세요.')
        if data.get('evaluation'):
            evaluation = CAPAEvaluation.objects.filter(pk=data['evaluation'],capa__in=capas).first()
            if not evaluation or not evaluation.evidence.exists() or evaluation != evaluation.capa.evaluations.order_by('-pk').first(): raise ValidationError('연결 CAPA의 최신 효과성 평가를 선택하세요.')
            payload.update(evaluated_on=str(evaluation.evaluated_on),verdict=evaluation.verdict,evidence=list(evaluation.evidence.values_list('pk',flat=True)))
        else:
            if not recalls.exists(): raise ValidationError('기존 CAPA 효과성 평가를 선택하세요.')
            checked = day(data.get('evaluated_on'))
            if checked>timezone.localdate() or data.get('verdict') not in ('PASS','FAIL'): raise ValidationError('효과 확인일·판정이 올바르지 않습니다.')
            files = evidence(user,data.get('evidence',[]),ids)
            if not files: raise ValidationError('효과 확인 증빙이 필요합니다.')
            if Attachment.objects.filter(pk__in=[f['id'] for f in files],purpose='ADMIN').exists():
                raise ValidationError('행정 증빙은 조치 효과성 근거로 사용할 수 없습니다.')
            payload.update(evaluated_on=str(checked),verdict=data['verdict'],evidence=files,recall_ids=list(recalls.values_list('pk',flat=True)))
        status = 'REVIEW' if payload['verdict']=='FAIL' else 'CLOSED' if signal.status=='CLOSED' else 'ACTION'
    if kind == 'CLOSE': closure_check(signal); status='CLOSED'
    if kind == 'REOPEN' and signal.status != 'CLOSED': raise ValidationError('종결 상태만 재검토할 수 있습니다.')
    record = SignalTracking.objects.create(signal=signal,actor=user,request_key=key,request_hash=fingerprint,kind=kind,data=payload,source_case_id=payload.get("complaint"),capa=capa,recall=recall,evaluation=evaluation)
    review_signal(user,pk,status,assignee,note,capa.pk if capa else None,recall.pk if recall else None,_tracking=True)
    if kind == 'INVESTIGATE' and signal.task_id:
        from .workflow import save_task
        task=signal.task
        task.refresh_from_db()
        task.due_at=timezone.make_aware(datetime.combine(day(payload['due_on']),time(23,59,59)),timezone.get_current_timezone())
        save_task(task,user)
    audit(user,'SIGNAL_TRACK',record,after={'kind':kind,'signal':pk})
    return record
