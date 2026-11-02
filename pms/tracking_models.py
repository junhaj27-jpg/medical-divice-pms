"""Append-only workflow records; source evidence and published snapshots are retained."""
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


class FrozenQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('보존 기록은 일괄 수정할 수 없습니다. 새 기록을 생성하세요.')

    def delete(self):
        raise ValidationError('보존 기록은 일괄 삭제할 수 없습니다.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('보존 기록은 일괄 수정할 수 없습니다. 새 기록을 생성하세요.')

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                    update_conflicts=False, update_fields=None, unique_fields=None):
        if update_conflicts:
            raise ValidationError('충돌한 보존 기록을 덮어쓸 수 없습니다.')
        return super().bulk_create(objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
            update_conflicts=False, update_fields=update_fields, unique_fields=unique_fields)


class FrozenRecord(models.Model):
    objects = FrozenQuerySet.as_manager()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    request_key = models.UUIDField(unique=True)
    request_hash = models.CharField(max_length=64)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk: raise ValidationError('보존 기록은 수정할 수 없습니다. 새 기록을 생성하세요.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('보존 기록은 삭제할 수 없습니다.')


class SignalTracking(FrozenRecord):
    source_case=models.ForeignKey("CustomerComplaint",null=True,on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["signal","kind","source_case"],condition=models.Q(kind__in=["DRAFT_CAPA","DRAFT_RECALL"]),name="unique_signal_action_draft")]
    signal = models.ForeignKey('SafetySignal', on_delete=models.PROTECT, related_name='tracking')
    kind = models.CharField(max_length=24)
    data = models.JSONField()
    capa = models.ForeignKey('CAPA', null=True, on_delete=models.PROTECT)
    recall = models.ForeignKey('Recall', null=True, on_delete=models.PROTECT)
    evaluation = models.ForeignKey('CAPAEvaluation', null=True, on_delete=models.PROTECT)


class SubmissionVersion(FrozenRecord):
    report = models.ForeignKey('RegulatoryReport', on_delete=models.PROTECT, related_name='submissions')
    version = models.PositiveIntegerField()
    report_kind = models.CharField(max_length=12, choices=[('INITIAL','최초 보고'),('FOLLOWUP','추가 보고'),('FINAL','최종 보고')])
    artifact = models.ForeignKey('ReportArtifact', on_delete=models.PROTECT)
    snapshot = models.JSONField()
    content_hash = models.CharField(max_length=64)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['report','version'], name='unique_submission_version')]


class SubmissionEvent(FrozenRecord):
    submission = models.ForeignKey(SubmissionVersion, on_delete=models.PROTECT, related_name='events')
    state = models.CharField(max_length=24)
    data = models.JSONField()


class PMSPeriodicReport(FrozenRecord):
    pdf_content = models.BinaryField(null=True, editable=False)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    stage=models.CharField(max_length=8,default="DRAFT",choices=[("DRAFT","작성 초안"),("FINAL","확정")])
    source=models.ForeignKey("self",null=True,on_delete=models.PROTECT)
    device = models.ForeignKey('MedicalDevice', on_delete=models.PROTECT)
    start = models.DateField()
    end = models.DateField()
    is_example = models.BooleanField(default=False)
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    content_hash = models.CharField(max_length=64)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+')
    review_note = models.TextField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['device','start','end','is_example','version'], name='unique_pms_period_version'),models.UniqueConstraint(fields=['source'],condition=models.Q(stage='FINAL'),name='unique_final_period_source')]


class DuplicateReview(FrozenRecord):
    complaint = models.ForeignKey('CustomerComplaint', on_delete=models.PROTECT, related_name='duplicate_reviews')
    other = models.ForeignKey('CustomerComplaint', on_delete=models.PROTECT, related_name='+')
    verdict = models.CharField(max_length=12)
    reason = models.TextField()
