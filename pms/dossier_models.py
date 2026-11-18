"""Versioned authoring over the existing writing projects and immutable DentalDrafts."""
from django.db import models
from django.conf import settings
from .history import AppendOnlyRecord

class RADocument(AppendOnlyRecord):
    project=models.ForeignKey('DentalProject',on_delete=models.PROTECT,related_name='ra_documents')
    document_type=models.CharField(max_length=24)
    country=models.CharField(max_length=2)
    language=models.CharField(max_length=8)
    creator=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    def __str__(self):return f'{self.project.device} / {self.document_type} / {self.country} / {self.language}'

class RADocumentRevision(AppendOnlyRecord):
    document=models.ForeignKey(RADocument,on_delete=models.PROTECT,related_name='revisions')
    draft=models.OneToOneField('DentalDraft',on_delete=models.PROTECT,related_name='ra_revision')
    number=models.PositiveIntegerField()
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    reason=models.CharField(max_length=2000)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['document','number'],name='ra_document_revision_number')]

class RADocumentValidation(AppendOnlyRecord):
    revision=models.ForeignKey(RADocumentRevision,on_delete=models.PROTECT,related_name='validations')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    fingerprint=models.CharField(max_length=64)
    findings=models.JSONField()
    context=models.JSONField()

class RADocumentReview(AppendOnlyRecord):
    revision=models.ForeignKey(RADocumentRevision,on_delete=models.PROTECT,related_name='review_events')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    state=models.CharField(max_length=24)
    reason=models.CharField(max_length=2000)
    validation=models.ForeignKey(RADocumentValidation,on_delete=models.PROTECT,null=True)

class RASourceImpactReview(AppendOnlyRecord):
    revision=models.ForeignKey(RADocumentRevision,on_delete=models.PROTECT,null=True,related_name='impact_events')
    adoption=models.ForeignKey('SearchEvidenceAdoption',on_delete=models.PROTECT,null=True,related_name='impact_events')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    section=models.CharField(max_length=240)
    fingerprint=models.CharField(max_length=64)
    state=models.CharField(max_length=20)
    reason=models.CharField(max_length=2000)
    snapshot=models.JSONField()
    class Meta:
        constraints=[models.CheckConstraint(condition=(models.Q(revision__isnull=False,adoption__isnull=True)|models.Q(revision__isnull=True,adoption__isnull=False)),name='ra_impact_one_target')]
