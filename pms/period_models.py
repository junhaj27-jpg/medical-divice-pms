"""Aggregate-only, append-only PMS analysis and review history."""
import uuid
from django.db import models
from django.conf import settings
from .history import AppendOnlyRecord

class PMSPeriodSnapshot(AppendOnlyRecord):
    request_key=models.UUIDField(default=uuid.uuid4,unique=True)
    device=models.ForeignKey('MedicalDevice',on_delete=models.PROTECT)
    market=models.CharField(max_length=2)
    criteria=models.JSONField()
    result=models.JSONField()
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at','-pk']
        indexes=[models.Index(fields=['device','market','created_at'],name='pms_period_scope_time')]

class PMSPeriodComment(AppendOnlyRecord):
    snapshot=models.ForeignKey(PMSPeriodSnapshot,on_delete=models.PROTECT,related_name='comments')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    note=models.TextField(max_length=4000)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:ordering=['created_at','pk']

class PMSPeriodAction(AppendOnlyRecord):
    KINDS=[('INVESTIGATION','추가 조사'),('CAPA','CAPA 검토')]
    snapshot=models.ForeignKey(PMSPeriodSnapshot,on_delete=models.PROTECT,related_name='actions')
    kind=models.CharField(max_length=16,choices=KINDS)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['snapshot','kind'],name='pms_period_action_unique')]
