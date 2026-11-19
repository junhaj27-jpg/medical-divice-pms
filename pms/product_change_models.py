"""Proposed MRI changes, separate from implementation and regulatory-source amendments."""
from django.db import models
from django.conf import settings
from .history import AppendOnlyRecord

class MRIProductChange(AppendOnlyRecord):
    device=models.ForeignKey('MedicalDevice',on_delete=models.PROTECT,related_name='mri_change_requests')
    kind=models.CharField(max_length=12,choices=[('SOFTWARE','소프트웨어 버전'),('LABEL','라벨')])
    before_value=models.TextField(max_length=4000)
    after_value=models.TextField(max_length=4000)
    reason=models.TextField(max_length=4000)
    planned_on=models.DateField()
    requested_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    requested_at=models.DateTimeField(auto_now_add=True)
    request_key=models.UUIDField(unique=True)
    request_hash=models.CharField(max_length=64)
    product_snapshot=models.JSONField()

class MRIChangeMarket(models.Model):
    change=models.ForeignKey(MRIProductChange,on_delete=models.PROTECT,related_name='market_reviews')
    country=models.CharField(max_length=2)
    snapshot=models.JSONField()
    version=models.PositiveIntegerField(default=1)
    status=models.CharField(max_length=16,default='IN_REVIEW')
    def save(self,*args,**kwargs):
        if self.pk:
            from django.core.exceptions import ValidationError
            old=type(self).objects.get(pk=self.pk)
            if (old.change_id,old.country,old.snapshot)!=(self.change_id,self.country,self.snapshot):raise ValidationError('검토 요청 당시 시장·문서 스냅샷은 변경할 수 없습니다.')
        return super().save(*args,**kwargs)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['change','country'],name='mri_change_market_unique')]

class MRIChangeDecision(AppendOnlyRecord):
    review=models.ForeignKey(MRIChangeMarket,on_delete=models.PROTECT,related_name='decisions')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    decisions=models.JSONField()
    targets=models.JSONField()
    rationale=models.TextField(max_length=4000)
    complete=models.BooleanField(default=False)
    version=models.PositiveIntegerField()
    class Meta:
        constraints=[models.UniqueConstraint(fields=['review','version'],name='mri_change_decision_version')]

class MRIChangeAction(AppendOnlyRecord):
    review=models.ForeignKey(MRIChangeMarket,on_delete=models.PROTECT,related_name='actions')
    action_type=models.CharField(max_length=12,choices=[('DOCUMENT','문서 개정'),('EVIDENCE','시험 증빙 보완')])
    target_key=models.CharField(max_length=80)
    target_snapshot=models.JSONField()
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['review','action_type','target_key'],name='mri_change_action_unique')]
