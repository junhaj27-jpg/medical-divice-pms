"""Application-level append-only records. Bulk SQL still requires restricted DB access."""
from django.core.exceptions import ValidationError
from django.db import models

class AppendOnlyRecord(models.Model):
    class Meta:
        abstract=True
    def save(self,*args,**kwargs):
        if self.pk: raise ValidationError('이력은 덮어쓸 수 없습니다. 새 기록을 추가하세요.')
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs):
        raise ValidationError('이력은 삭제할 수 없습니다.')
