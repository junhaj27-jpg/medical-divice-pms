from django.conf import settings
from django.db import models

from .history import AppendOnlyRecord


class DentalGuide(AppendOnlyRecord):
    issued_on = models.DateField(unique=True)
    status = models.CharField(max_length=20)
    url = models.URLField()
    checked_on = models.DateField()
    sha256 = models.CharField(max_length=64)
    sections = models.JSONField()


class DentalProject(models.Model):
    device = models.OneToOneField("MedicalDevice", on_delete=models.PROTECT)
    guide = models.ForeignKey(DentalGuide, on_delete=models.PROTECT)
    specification = models.JSONField()


class DentalEvidence(AppendOnlyRecord):
    project = models.ForeignKey(DentalProject, on_delete=models.PROTECT, related_name="evidence")
    document = models.ForeignKey("ControlledDocument", on_delete=models.PROTECT)
    section = models.CharField(max_length=10)
    details = models.JSONField()


class DentalDraft(AppendOnlyRecord):
    project = models.ForeignKey(DentalProject, on_delete=models.PROTECT, related_name="drafts")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    snapshot = models.JSONField()


class DentalDraftReview(AppendOnlyRecord):
    draft = models.ForeignKey(DentalDraft, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(max_length=2000)
