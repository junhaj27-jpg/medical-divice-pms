from django.db import models
from django.conf import settings
from .history import AppendOnlyRecord

class ReviewTaskContext(models.Model):
    task=models.OneToOneField('WorkTask',on_delete=models.PROTECT,related_name='review_context')
    origin_key=models.CharField(max_length=64,unique=True)
    origin_kind=models.CharField(max_length=24)
    product=models.ForeignKey('MedicalDevice',on_delete=models.PROTECT)
    country=models.CharField(max_length=2)
    revision=models.ForeignKey('RADocumentRevision',null=True,on_delete=models.PROTECT)
    adoption=models.ForeignKey('SearchEvidenceAdoption',null=True,on_delete=models.PROTECT)
    evaluation=models.ForeignKey('CAPAEvaluation',null=True,on_delete=models.PROTECT)
    parent_task=models.ForeignKey('WorkTask',null=True,on_delete=models.PROTECT,related_name='review_followups')
    source_snapshot=models.JSONField()
    criteria=models.TextField(max_length=4000)
    evidence_required=models.BooleanField(default=True)
    deadline_snapshot=models.JSONField()
    version=models.PositiveIntegerField(default=1)
    cycle=models.PositiveIntegerField(default=1)
    completed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.PROTECT,related_name='+')
    completed_at=models.DateTimeField(null=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=(models.Q(revision__isnull=False,adoption__isnull=True,evaluation__isnull=True)|models.Q(revision__isnull=True,adoption__isnull=False,evaluation__isnull=True)|models.Q(revision__isnull=True,adoption__isnull=True,evaluation__isnull=False)),name='review_task_one_origin')]

class ReviewTaskEvidence(AppendOnlyRecord):
    task=models.ForeignKey('WorkTask',on_delete=models.PROTECT,related_name='review_evidence')
    cycle=models.PositiveIntegerField(default=1)
    attachment=models.ForeignKey('Attachment',on_delete=models.PROTECT)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    note=models.CharField(max_length=2000)
    snapshot=models.JSONField()
    class Meta:
        constraints=[models.UniqueConstraint(fields=['task','attachment','cycle'],name='review_task_evidence_unique')]
