"""Isolated PMS analysis cohort; existing complaint workflows remain unchanged."""
from django.conf import settings
from django.db import models


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
    origin = models.CharField(max_length=12, default='CSV', choices=[('CSV','CSV'),('INTERNAL','내부 사건')])
    source_case = models.ForeignKey('CustomerComplaint', null=True, blank=True, on_delete=models.PROTECT, related_name='analysis_records')
    source_hash = models.CharField(max_length=64, blank=True)
    source_version = models.PositiveIntegerField(null=True)
    supersedes = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='correction')
    is_current = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['source_case','source_hash'], condition=models.Q(origin='INTERNAL'), name='unique_internal_source_version'),
                       models.UniqueConstraint(fields=['source_case'], condition=models.Q(origin='INTERNAL',is_current=True), name='unique_current_internal_case')]



class AnalysisReview(models.Model):
    key = models.CharField(max_length=64, unique=True)
    snapshot = models.JSONField()
    status = models.CharField(max_length=12, choices=[('NEW', '신규'), ('REVIEW', '검토 중'), ('ACTION', '조치 필요'), ('CLOSED', '종료')], default='NEW')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)


class AnalysisReviewHistory(models.Model):
    review = models.ForeignKey(AnalysisReview, on_delete=models.PROTECT, related_name='history')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    before = models.CharField(max_length=12, blank=True)
    after = models.CharField(max_length=12)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class SeriousnessConfirmation(models.Model):
    complaint = models.ForeignKey('CustomerComplaint', on_delete=models.PROTECT, related_name='seriousness_confirmations')
    value = models.CharField(max_length=12, choices=[('SERIOUS','중대'),('NON_SERIOUS','비중대'),('UNKNOWN','미상')])
    reason = models.TextField(max_length=2000)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class AnalysisReport(models.Model):
    key = models.CharField(max_length=64, unique=True)
    number = models.CharField(max_length=80, unique=True)


class AnalysisArtifact(models.Model):
    report = models.ForeignKey(AnalysisReport, on_delete=models.PROTECT, related_name='artifacts')
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='analysis-reports/%Y/%m/')
    sha256 = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['report','version'], name='unique_analysis_pdf_version')]
