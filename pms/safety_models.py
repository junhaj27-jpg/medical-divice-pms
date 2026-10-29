from django.conf import settings
from django.db import models


class SafetySignal(models.Model):
    key = models.CharField(max_length=64, unique=True)
    # Scope is a user-specific cohort for STAFF, shared professional cohort otherwise.
    scope = models.CharField(max_length=80)
    snapshot = models.JSONField()
    status = models.CharField(max_length=12, default="NEW", choices=[
        ("NEW", "신규"), ("REVIEW", "검토 중"), ("ACTION", "조치 연결"), ("CLOSED", "종결")])
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    task = models.OneToOneField("pms.WorkTask", null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class SafetyReview(models.Model):
    signal = models.ForeignKey(SafetySignal, on_delete=models.PROTECT, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    before = models.CharField(max_length=12)
    after = models.CharField(max_length=12)
    note = models.TextField()
    links = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
