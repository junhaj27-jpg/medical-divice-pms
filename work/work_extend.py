from pathlib import Path
p=Path('pms/analysis_models.py')
s=p.read_text(encoding='utf-8').replace('    narrative = models.TextField(blank=True)','''    narrative = models.TextField(blank=True)
    origin = models.CharField(max_length=12, default='CSV', choices=[('CSV','CSV'),('INTERNAL','내부 사건')])
    source_case = models.ForeignKey('CustomerComplaint', null=True, blank=True, on_delete=models.PROTECT, related_name='analysis_records')
    source_hash = models.CharField(max_length=64, blank=True)
    source_version = models.PositiveIntegerField(null=True)
    supersedes = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='correction')
    is_current = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['source_case','source_hash'], condition=models.Q(origin='INTERNAL'), name='unique_internal_source_version'),
                       models.UniqueConstraint(fields=['source_case'], condition=models.Q(origin='INTERNAL',is_current=True), name='unique_current_internal_case')]
''')
s+='''

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
'''
p.write_text(s,encoding='utf-8')
p=Path('pms/models.py');s=p.read_text(encoding='utf-8').replace('from .analysis_models import AnalysisImport, AnalysisRecord, AnalysisReview, AnalysisReviewHistory','from .analysis_models import AnalysisImport, AnalysisRecord, AnalysisReview, AnalysisReviewHistory, SeriousnessConfirmation, AnalysisReport, AnalysisArtifact');s=s.replace('class RegulatoryImpact(models.Model):','class RegulatoryImpact(models.Model):\n    submission_key=models.UUIDField(null=True,blank=True,unique=True)');p.write_text(s,encoding='utf-8')
p=Path('pms/approval_integrity.py');s=p.read_text(encoding='utf-8').replace("    return {'schema': 1", "    confirmations = list(case.seriousness_confirmations.order_by('pk').values('id','value','reason','actor_id','created_at'))\n    if confirmations: scopes['seriousness_confirmation'] = digest(confirmations)\n    return {'schema': 1");p.write_text(s,encoding='utf-8')
p=Path('pms/analysis.py');s=p.read_text(encoding='utf-8').replace('from django.db import IntegrityError, transaction','from django.db import IntegrityError, transaction\nfrom django.db.models import Q');s=s.replace("qs = AnalysisRecord.objects.filter(batch__is_example=data['example'] == 'sample')","qs = AnalysisRecord.objects.filter(batch__is_example=data['example'] == 'sample').filter(Q(origin='CSV') | Q(is_current=True))");s=s.replace('records=current, groups=', 'records=current, previous_records=previous, groups=');s=s.replace("evidence=evidence)","evidence=evidence, content_hashes=[digest([r.pk,r.raw,r.seriousness,r.source_hash]) for r in current + previous if key(r)==device])");p.write_text(s,encoding='utf-8')
