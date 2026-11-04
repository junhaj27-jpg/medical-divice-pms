from django.conf import settings
from django.db import models

from .history import AppendOnlyRecord

USER = settings.AUTH_USER_MODEL


class ForeignApplication(models.Model):
    class Market(models.TextChoices):
        US = "US", "미국"
        EU = "EU", "EU"

    class Stage(models.TextChoices):
        PREPARATION = "PREPARATION", "준비 중"
        REVIEW = "REVIEW", "내부 검토"
        SUBMITTED = "SUBMITTED", "제출 완료"
        RESULT = "RESULT", "결과 기록"

    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    profile = models.ForeignKey("pms.RegulatoryProfile", on_delete=models.PROTECT)
    market = models.CharField("시장", max_length=2, choices=Market.choices)
    title = models.CharField("신청 건", max_length=200)
    kind = models.CharField("신청 유형", max_length=8, choices=[("NEW", "신규"), ("CHANGE", "변경"), ("RENEWAL", "갱신")])
    previous = models.ForeignKey("self", verbose_name="이전 신청", on_delete=models.PROTECT, null=True, blank=True)
    model_scope = models.CharField("적용 모델", max_length=160, blank=True)
    release = models.ForeignKey("pms.SoftwareRelease", verbose_name="소프트웨어 릴리스", on_delete=models.PROTECT, null=True, blank=True)
    intended_use = models.TextField("사용목적")
    classification = models.CharField("검토 중인 분류", max_length=160, blank=True)
    pathway = models.CharField("검토 중인 경로", max_length=160, blank=True)
    rationale = models.TextField("판단 근거")
    owner = models.ForeignKey(USER, verbose_name="담당자", on_delete=models.PROTECT)
    target_on = models.DateField("목표 제출일", null=True, blank=True)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.PREPARATION)
    is_example = models.BooleanField("가상 시연 데이터", default=False)

    def __str__(self):
        return self.title


class ForeignDocument(models.Model):
    application = models.ForeignKey(ForeignApplication, on_delete=models.PROTECT, related_name="documents")
    title = models.CharField("문서명", max_length=200)
    version = models.CharField("버전", max_length=80, blank=True)
    owner = models.ForeignKey(USER, verbose_name="담당자", on_delete=models.PROTECT)
    applicability = models.CharField("적용 여부", max_length=12, choices=[("UNVERIFIED", "미확정"), ("APPLIES", "적용"), ("EXCLUDED", "비적용")], default="UNVERIFIED")
    rationale = models.TextField("적용 판단 근거", blank=True)
    status = models.CharField("준비 상태", max_length=8, choices=[("DRAFT", "준비 중"), ("READY", "준비 완료")], default="DRAFT")
    evidence = models.ForeignKey("pms.Attachment", verbose_name="증빙", on_delete=models.PROTECT, null=True, blank=True)


class ForeignSubmission(AppendOnlyRecord):
    application = models.ForeignKey(ForeignApplication, on_delete=models.PROTECT, related_name="submissions")
    submitted_on = models.DateField("제출일")
    reference = models.CharField("참조번호", max_length=160)
    evidence = models.ForeignKey("pms.Attachment", verbose_name="제출 증빙", on_delete=models.PROTECT)
    approval = models.OneToOneField("pms.Approval", on_delete=models.PROTECT)
    manifest = models.JSONField()


class ForeignSupplement(models.Model):
    application = models.ForeignKey(ForeignApplication, on_delete=models.PROTECT, related_name="supplements")
    requested_on = models.DateField("요청일")
    due_on = models.DateField("회신 기한")
    basis = models.TextField("요청 내용 및 기한 근거")
    task = models.OneToOneField("pms.WorkTask", on_delete=models.PROTECT)
    response = models.ForeignKey("pms.Attachment", verbose_name="답변 증빙", on_delete=models.PROTECT, null=True, blank=True)
    responded_on = models.DateField("회신일", null=True, blank=True)


class ForeignResult(AppendOnlyRecord):
    application = models.OneToOneField(ForeignApplication, on_delete=models.PROTECT, related_name="result")
    kind = models.CharField("결과 유형", max_length=100)
    issuer = models.CharField("발행 주체", max_length=200)
    issued_on = models.DateField("결과일")
    reference = models.CharField("문서 번호", max_length=160)
    expires_on = models.DateField("유효기간 종료일", null=True, blank=True)
    evidence = models.ForeignKey("pms.Attachment", verbose_name="결과 증빙", on_delete=models.PROTECT)

