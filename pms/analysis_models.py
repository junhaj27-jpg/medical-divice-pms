"""Isolated PMS analysis cohort; existing complaint workflows remain unchanged."""
from django.conf import settings
from django.db import models
from .history import AppendOnlyRecord


class AnalysisImport(models.Model):
    filename = models.CharField(max_length=255)
    original = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    is_example = models.BooleanField(default=False)
    errors = models.JSONField(default=list)
    accepted = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class AnalysisRecord(models.Model):
    batch = models.ForeignKey(AnalysisImport, on_delete=models.PROTECT, related_name='records')
    row_number = models.PositiveIntegerField()
    raw = models.JSONField()
    source = models.CharField(max_length=200)
    record_id = models.CharField(max_length=200, blank=True)
    identity = models.CharField(max_length=64, unique=True)
    device = models.CharField(max_length=200)
    manufacturer = models.CharField(max_length=200, blank=True)
    model = models.CharField(max_length=200, blank=True)
    occurred_on = models.DateField(null=True)
    reported_on = models.DateField()
    event_type = models.CharField(max_length=200)
    seriousness = models.CharField(max_length=12, choices=[('SERIOUS', '중대'), ('NON_SERIOUS', '비중대'), ('UNKNOWN', '미상')])
    narrative = models.TextField(blank=True)


    class Meta:
        indexes=[models.Index(fields=['reported_on'],name='analysis_reported_period'),models.Index(fields=['occurred_on'],name='analysis_occurred_period')]
        constraints=[models.UniqueConstraint(fields=['batch','row_number'],name='unique_import_row'),models.CheckConstraint(condition=models.Q(seriousness__in=['SERIOUS','NON_SERIOUS','UNKNOWN']),name='analysis_seriousness_valid')]


class AnalysisReview(models.Model):
    key = models.CharField(max_length=64, unique=True)
    snapshot = models.JSONField()
    status = models.CharField(max_length=12, choices=[('NEW', '신규'), ('REVIEW', '검토 중'), ('ACTION', '조치 필요'), ('CLOSED', '종료')], default='NEW')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)


class AnalysisReviewHistory(AppendOnlyRecord):
    review = models.ForeignKey(AnalysisReview, on_delete=models.PROTECT, related_name='history')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    before = models.CharField(max_length=12, blank=True)
    after = models.CharField(max_length=12)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
