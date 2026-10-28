"""Validated ingestion and deterministic count-based signals; no external AI calls."""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import date, timedelta

from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .analysis_models import AnalysisImport, AnalysisRecord, AnalysisReview, AnalysisReviewHistory
from .file_security import normalized_name
from .services import role

HEADERS = ['source', 'record_id', 'device', 'manufacturer', 'model', 'occurred_on', 'reported_on', 'event_type', 'seriousness', 'narrative']


def require_analyst(user):
    if not user.is_authenticated or role(user) not in ('RA_QA', 'ADMIN'):
        raise PermissionDenied('분석 데이터는 RA/QA 또는 관리자만 접근할 수 있습니다.')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def parse_row(raw):
    data = {key: value.strip() for key, value in raw.items()}
    errors = []
    for key in ('source', 'device', 'reported_on', 'event_type'):
        if not data[key]: errors.append(f'{key}: 필수값 누락')
    for key in HEADERS:
        if len(data[key]) > (10000 if key == 'narrative' else 200): errors.append(f'{key}: 길이 제한 초과')
        if '\x00' in data[key]: errors.append(f'{key}: NUL 문자는 허용하지 않습니다.')
    for key in ('occurred_on', 'reported_on'):
        value = data[key]
        data[key] = None
        if value:
            try:
                if len(value) != 10 or value[4] != '-' or value[7] != '-': raise ValueError()
                data[key] = date.fromisoformat(value)
                if data[key] > timezone.localdate(): errors.append(f'{key}: 미래 날짜')
            except ValueError: errors.append(f'{key}: YYYY-MM-DD 날짜 형식 오류')
    if data['occurred_on'] and data['reported_on'] and data['occurred_on'] > data['reported_on']:
        errors.append('발생일이 보고일보다 늦습니다.')
    seriousness = data['seriousness'].upper() or 'UNKNOWN'
    data['seriousness'] = seriousness
    if seriousness not in ('SERIOUS', 'NON_SERIOUS', 'UNKNOWN'): errors.append('seriousness: 허용값 SERIOUS/NON_SERIOUS/UNKNOWN')
    if errors: raise ValidationError(errors)
    return data


@transaction.atomic
def ingest(upload, user, is_example=False):
    require_analyst(user)
    name = normalized_name(upload.name)
    limit = min(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 5 * 1024 * 1024)
    if not name.lower().endswith('.csv'): raise ValidationError('UTF-8 CSV 파일만 허용합니다.')
    content = upload.read(limit + 1)
    if not content or len(content) > limit: raise ValidationError('빈 파일이거나 파일 크기 제한을 초과했습니다.')
    try:
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig'), newline=''), strict=True)
        if reader.fieldnames != HEADERS: raise ValidationError('CSV 열과 순서가 샘플과 일치해야 합니다: ' + ', '.join(HEADERS))
        rows = []
        for raw in reader:
            if len(rows) >= 10000: raise ValidationError('최대 10000행까지 허용합니다.')
            rows.append((reader.line_num, raw))
    except (UnicodeError, csv.Error): raise ValidationError('UTF-8 인코딩 또는 CSV 구문 오류입니다.') from None
    batch = AnalysisImport.objects.create(filename=name, original=content, sha256=hashlib.sha256(content).hexdigest(), actor=user, is_example=is_example)
    errors = []
    for number, raw in rows:
        try:
            if None in raw or any(value is None for value in raw.values()): raise ValidationError('열 개수가 일치하지 않습니다.')
            data = parse_row(raw)
            identity_data = [data['source'], data['record_id']] if data['record_id'] else [str(data[k]) for k in HEADERS if k not in ('record_id', 'seriousness')]
            identity = digest([is_example, bool(data['record_id']), identity_data])
            try:
                with transaction.atomic():
                    AnalysisRecord.objects.create(batch=batch, row_number=number, raw=raw, identity=identity, **data)
            except IntegrityError:
                raise ValidationError('출처 ID 중복' if data['record_id'] else '식별자 없는 중복 의심: 정제 내용 일치') from None
        except ValidationError as exc:
            errors.append({'row': number, 'reasons': exc.messages})
    if not rows: errors.append({'row': 1, 'reasons': ['데이터 행이 없습니다.']})
    batch.errors = errors
    batch.accepted = batch.records.count()
    batch.save(update_fields=['errors', 'accepted'])
    return batch


class AnalysisFilter(forms.Form):
    basis = forms.ChoiceField(label='날짜 기준', choices=[('reported_on', '보고일'), ('occurred_on', '발생일')], initial='reported_on')
    start = forms.DateField(label='시작일', widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(label='종료일', widget=forms.DateInput(attrs={'type': 'date'}))
    example = forms.ChoiceField(label='데이터 구분', choices=[('real', '실제'), ('sample', '샘플')])
    device = forms.CharField(label='기기명', required=False, max_length=200)
    manufacturer = forms.CharField(label='제조사', required=False, max_length=200)
    model = forms.CharField(label='모델', required=False, max_length=200)
    event_type = forms.CharField(label='사건 유형', required=False, max_length=200)
    source = forms.CharField(label='출처', required=False, max_length=200)
    seriousness = forms.ChoiceField(label='중대성', required=False, choices=[('', '전체'), ('SERIOUS', '중대'), ('NON_SERIOUS', '비중대'), ('UNKNOWN', '미상')])
    minimum = forms.IntegerField(label='최소 보고 건수', min_value=1, max_value=1000000, initial=3)
    threshold = forms.IntegerField(label='증가 임계값 (%)', min_value=1, max_value=100000, initial=100)

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end'):
            if data['start'] > data['end']: raise forms.ValidationError('시작일이 종료일보다 늦습니다.')
            if data['start'].year < 1901: raise forms.ValidationError('1901년 이후 날짜를 사용하세요.')
            if (data['end'] - data['start']).days > 3660: raise forms.ValidationError('최대 분석 기간은 3661일입니다.')
        return data


def default_filters():
    today = timezone.localdate()
    return dict(basis='reported_on', start=(today - timedelta(days=29)).isoformat(), end=today.isoformat(), example='real', minimum=3, threshold=100)


def analyze(data):
    qs = AnalysisRecord.objects.filter(batch__is_example=data['example'] == 'sample')
    for field in ('device', 'manufacturer', 'model', 'event_type', 'source'):
        if data.get(field): qs = qs.filter(**{field + '__icontains': data[field]})
    if data.get('seriousness'): qs = qs.filter(seriousness=data['seriousness'])
    basis = data['basis']
    start, end = data['start'], data['end']
    previous_end = start - timedelta(days=1)
    previous_start = start - (end - start) - timedelta(days=1)
    current = list(qs.filter(**{basis + '__range': (start, end)}).order_by(basis, 'pk'))
    previous = list(qs.filter(**{basis + '__range': (previous_start, previous_end)}))
    key = lambda row: (row.device, row.manufacturer, row.model)
    now_counts, old_counts = Counter(map(key, current)), Counter(map(key, previous))
    groups, signals = [], []
    serial_filters = {k: v.isoformat() if isinstance(v, date) else v for k, v in data.items()}
    for device in sorted(now_counts.keys() | old_counts.keys()):
        count, old = now_counts[device], old_counts[device]
        increase = round((count - old) / old * 100, 1) if old else None
        group = dict(device=device, count=count, previous=old, increase=increase)
        groups.append(group)
        if count >= data['minimum'] and (not old or (count - old) * 100 >= old * data['threshold']):
            evidence = [dict(id=row.pk, source=row.source, record_id=row.record_id, quote=row.narrative, row=row.row_number, batch=row.batch_id) for row in current if key(row) == device]
            snapshot = dict(filters=serial_filters, device=list(device), count=count, previous=old, increase=increase, previous_start=previous_start.isoformat(), previous_end=previous_end.isoformat(), evidence=evidence)
            signal_key = digest(snapshot)
            signals.append(dict(key=signal_key, snapshot=snapshot, group=group, review=AnalysisReview.objects.filter(key=signal_key).first()))
    return dict(records=current, groups=groups, signals=signals, total=len(current), previous_total=len(previous), previous_start=previous_start, previous_end=previous_end, seriousness=dict(Counter(row.get_seriousness_display() for row in current)), periods=dict(sorted(Counter(str(getattr(row, basis))[:7] for row in current).items())), missing_dates=qs.filter(**{basis + '__isnull': True}).count(), sources=sorted({row.source for row in current}), generated_at=timezone.localtime())


@transaction.atomic
def save_review(user, signal, status, assignee, note):
    require_analyst(user)
    if status not in dict(AnalysisReview._meta.get_field('status').choices) or not note.strip() or len(note) > 4000:
        raise ValidationError('상태와 4000자 이내 검토 의견을 입력하세요.')
    if not assignee.is_active or role(assignee) not in ('RA_QA', 'ADMIN'):
        raise ValidationError('활성 RA/QA 또는 관리자 담당자를 선택하세요.')
    review, _ = AnalysisReview.objects.get_or_create(key=signal['key'], defaults={'snapshot': signal['snapshot'], 'assignee': assignee})
    review = AnalysisReview.objects.select_for_update().get(pk=review.pk)
    before = review.status
    review.status, review.assignee = status, assignee
    review.save()
    AnalysisReviewHistory.objects.create(review=review, actor=user, assignee=assignee, before=before, after=status, note=note.strip())
    return review


def csv_cell(value):
    value = '' if value is None else str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value
