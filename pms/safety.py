"""Internal complaint cohorts. No exposure denominator is inferred from LOT inventory."""
import hashlib
import json
from datetime import timedelta
from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone
from .models import CustomerComplaint, MedicalDevice, ProductLot, CAPA, Recall, WorkTask, Notification
from .safety_models import SafetySignal, SafetyReview
from .services import visible_complaints, role, audit


class SafetyFilter(forms.Form):
    start = forms.DateField(label="시작일", widget=forms.DateInput(attrs={"type":"date"}))
    end = forms.DateField(label="종료일", widget=forms.DateInput(attrs={"type":"date"}))
    device = forms.ModelChoiceField(label="제품", queryset=MedicalDevice.objects.none(), required=False)
    lot = forms.ModelChoiceField(label="LOT", queryset=ProductLot.objects.none(), required=False)
    complaint_type = forms.CharField(label="불만 유형 (정확히 일치)", required=False, max_length=50)
    risk = forms.ChoiceField(label="위험등급", required=False, choices=[("", "전체")]+[(x,x) for x in ("LOW","MEDIUM","HIGH","CRITICAL")])
    interval = forms.ChoiceField(label="집계", choices=[("week","주별"),("month","월별")])
    example = forms.ChoiceField(label="대상", choices=[("real","일반 사건"),("sample","테스트용 사건")])

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cases = visible_complaints(user)
        self.fields["device"].queryset = MedicalDevice.objects.filter(pk__in=cases.values("device_id"))
        self.fields["lot"].queryset = ProductLot.objects.filter(pk__in=cases.values("lot_id"))

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end"):
            if not 0 <= (data["end"]-data["start"]).days <= 730:
                raise forms.ValidationError("기간은 1~731일이어야 합니다.")
            if data["end"] > timezone.localdate():
                raise forms.ValidationError("미래 종료일은 사용할 수 없습니다.")
        if data.get("lot") and data.get("device") and data["lot"].device_id != data["device"].pk:
            raise forms.ValidationError("제품과 LOT가 일치하지 않습니다.")
        return data


def scope_for(user):
    if not user.is_authenticated: raise PermissionDenied
    return f"user:{user.pk}" if role(user) == "STAFF" else "professional"


def cohort(user, data):
    scope_for(user)
    qs = visible_complaints(user).filter(is_example=data["example"] == "sample")
    for field in ("device","lot","complaint_type"):
        if data.get(field): qs = qs.filter(**{field:data[field]})
    if data.get("risk"): qs = qs.filter(risk_assessment__level=data["risk"])
    return qs


def rule_reasons(count, previous, lot=False, urgent=0, rules=None):
    rules = rules or settings.SAFETY_RULES
    reasons = []
    if count >= rules["COUNT"]: reasons.append("기간 내 건수 임계치")
    if count >= rules["MINIMUM"] and previous and (count-previous)*100 >= previous*rules["INCREASE_PERCENT"]:
        reasons.append("이전 동일 길이 기간 대비 증가")
    if count >= rules["MINIMUM"] and previous == 0: reasons.append("이전 기간 0건 이후 신규 발생 (증가율 산정 불가)")
    if lot and count >= rules["LOT_COUNT"]: reasons.append("동일 LOT 반복 불만")
    if urgent: reasons.append("고위험 또는 중대 사건 발생")
    return reasons


def analyze_safety(user, data):
    qs = cohort(user, data)
    start, end = data["start"], data["end"]
    length = (end-start).days+1
    previous_end, previous_start = start-timedelta(days=1), start-timedelta(days=length)
    current = qs.filter(reported_on__range=(start,end)).order_by()
    previous = qs.filter(reported_on__range=(previous_start,previous_end)).order_by()
    old = {(r["device_id"],r["lot_id"],r["complaint_type"]):r["count"] for r in previous.values("device_id","lot_id","complaint_type").annotate(count=Count("pk"))}
    urgent = Q(risk_assessment__level__in=["HIGH","CRITICAL"]) | Q(adverse_event__serious=True)
    grouped = list(current.values("device_id","device__name","lot_id","lot__lot_number","complaint_type").annotate(count=Count("pk"),urgent=Count("pk",filter=urgent)))
    serial = {k:(v.pk if hasattr(v,"pk") else v.isoformat() if hasattr(v,"isoformat") else v) for k,v in data.items()}
    rules = dict(settings.SAFETY_RULES)
    for row in grouped:
        row["previous"] = old.get((row["device_id"],row["lot_id"],row["complaint_type"]),0)
        row["increase"] = round((row["count"]-row["previous"])*100/row["previous"],1) if row["previous"] else None
        row["reasons"] = rule_reasons(row["count"],row["previous"],row["lot_id"] is not None,row["urgent"],rules)
    trunc = TruncWeek if data["interval"] == "week" else TruncMonth
    timeline = list(current.annotate(bucket=trunc("reported_on")).values("bucket","device_id","lot_id").annotate(count=Count("pk")).order_by("bucket","device_id","lot_id"))
    return dict(total=current.count(), previous_total=previous.count(), urgent=current.filter(urgent).count(),
                high=current.filter(risk_assessment__level__in=["HIGH","CRITICAL"]).count(),
                serious=current.filter(adverse_event__serious=True).count(),
                previous_start=previous_start, previous_end=previous_end, groups=grouped, timeline=timeline,
                cases=current.select_related("device","lot","risk_assessment","adverse_event").order_by("reported_on","pk"),
                filters=serial, rules=rules, rate=None)


def signals_for(user):
    scope = scope_for(user)
    return SafetySignal.objects.filter(scope=scope).select_related("assignee","task")


@transaction.atomic
def detect(user, data):
    if role(user) not in ("RA_QA","ADMIN"): raise PermissionDenied
    result = analyze_safety(user,data)
    # Fetch evidence once, avoiding a query per product/LOT.
    evidence = list(result["cases"].values("pk","device_id","lot_id","complaint_type","reported_on","title","risk_assessment__level","adverse_event__serious"))
    created = []
    for row in result["groups"]:
        if not row["reasons"]: continue
        identity = dict(scope=scope_for(user), filters={k:v for k,v in result["filters"].items() if k!="interval"}, rules=result["rules"],
                        group=[row["device_id"],row["lot_id"],row["complaint_type"]])
        key = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        cases = [dict(c,reported_on=c["reported_on"].isoformat()) for c in evidence if (c["device_id"],c["lot_id"],c["complaint_type"]) == tuple(identity["group"])]
        snapshot = dict(identity, group=row, previous_start=result["previous_start"].isoformat(),previous_end=result["previous_end"].isoformat(),evidence=cases,rate=None)
        signal, fresh = SafetySignal.objects.get_or_create(key=key,defaults=dict(scope=scope_for(user),snapshot=snapshot,assignee=user))
        if fresh:
            task = WorkTask(complaint_id=cases[0]["pk"],assignee=user,title=f"안전 신호 #{signal.pk} 검토",description="검토 대상이며 확정 안전성 판단이 아닙니다.",due_at=timezone.now()+timedelta(days=settings.TASK_DUE_SOON_DAYS))
            from .workflow import save_task
            save_task(task,user);signal.task=task;signal.save(update_fields=["task"])
            Notification.objects.get_or_create(dedupe_key=f"safety:{signal.pk}:{user.pk}",defaults=dict(user=user,title=task.title,message=f"/safety/signals/{signal.pk}/",level="WARNING"))
            audit(user,"SAFETY_DETECT",signal,after={"rules":result["rules"],"count":row["count"]})
        created.append(signal)
    return created


@transaction.atomic
def review_signal(user, signal_id, status, assignee_id, note, capa_id=None, recall_id=None):
    if role(user) not in ("RA_QA","ADMIN"): raise PermissionDenied
    signal = signals_for(user).select_for_update(of=("self",)).get(pk=signal_id)
    if status not in dict(SafetySignal._meta.get_field("status").choices) or not note.strip() or len(note)>10000:
        raise ValidationError("상태와 검토 의견·사유가 필요합니다.")
    try:
        assignee_id=int(assignee_id)
        capa_id=int(capa_id) if capa_id else None
        recall_id=int(recall_id) if recall_id else None
    except (ValueError,TypeError):
        raise ValidationError("올바른 담당자·조치 번호를 입력하세요.") from None
    assignee = User.objects.filter(pk=assignee_id,is_active=True).first()
    if not assignee or role(assignee) not in ("RA_QA","ADMIN"): raise ValidationError("담당자는 활성 RA/QA 또는 관리자여야 합니다.")
    ids = [c["pk"] for c in signal.snapshot["evidence"]]
    links = {}
    for key, model, pk in (("capa",CAPA,capa_id),("recall",Recall,recall_id)):
        if pk:
            obj = model.objects.filter(pk=pk,complaint_id__in=ids).first()
            if not obj: raise ValidationError("신호의 연결 사건에 속한 기존 조치만 연결하세요.")
            links[key] = obj.pk
    if status == "ACTION" and not links: raise ValidationError("조치 연결에는 기존 CAPA 또는 리콜이 필요합니다.")
    SafetyReview.objects.create(signal=signal,actor=user,assignee=assignee,before=signal.status,after=status,note=note,links=links)
    before = signal.status
    previous_assignee = signal.assignee_id
    signal.status=status;signal.assignee=assignee;signal.save(update_fields=["status","assignee"])
    if signal.task:
        from .workflow import save_task
        signal.task.assignee=assignee
        signal.task.status="DONE" if status=="CLOSED" else "IN_PROGRESS" if status != "NEW" else "WAITING"
        save_task(signal.task,user)
    if before != status or previous_assignee != assignee.pk:
        Notification.objects.get_or_create(dedupe_key=f"safety:{signal.pk}:{assignee.pk}:{status}",defaults=dict(user=assignee,title=f"안전 신호 #{signal.pk} 검토 변경",message=f"/safety/signals/{signal.pk}/",level="INFO"))
    audit(user,"SAFETY_REVIEW",signal,after={"status":status})
    return signal
