"""Search-only derivatives. They never participate in rule approval or case assessment."""
from django.db import models
from .history import AppendOnlyRecord


class EULegalTextVersion(AppendOnlyRecord):
    document=models.ForeignKey('EULegalDocument',on_delete=models.PROTECT,related_name='search_text_versions')
    version=models.PositiveIntegerField()
    text=models.TextField()
    content_hash=models.CharField(max_length=64)
    original_hash=models.CharField(max_length=64)
    retrieved_at=models.DateTimeField(auto_now_add=True)
    official_url=models.URLField(max_length=1000)
    sections=models.JSONField(default=list)
    scope_description=models.CharField(max_length=500,default='공식 원문 본문')
    source_method=models.CharField(max_length=30,default='legacy')
    resolved_url=models.URLField(max_length=1500,blank=True)
    original_file=models.FileField(upload_to='eu_sources/',blank=True,max_length=255)
    verification=models.JSONField(default=dict)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['document','content_hash'],name='eu_search_text_content'),
                     models.UniqueConstraint(fields=['document','version'],name='eu_search_text_version')]


class SourceSearchPassage(AppendOnlyRecord):
    key=models.CharField(max_length=180,unique=True)
    regulation_chunk=models.ForeignKey('RegulationChunk',null=True,on_delete=models.PROTECT)
    fda_reference=models.ForeignKey('FDAReferenceVersion',null=True,on_delete=models.PROTECT)
    eu_text=models.ForeignKey(EULegalTextVersion,null=True,on_delete=models.PROTECT)
    section=models.CharField(max_length=240,blank=True)
    page=models.PositiveIntegerField(null=True)
    ordinal=models.PositiveIntegerField()
    text=models.TextField()
    content_hash=models.CharField(max_length=64)
    parent_hash=models.CharField(max_length=64)
    class Meta:
        constraints=[models.CheckConstraint(condition=(
            models.Q(regulation_chunk__isnull=False,fda_reference__isnull=True,eu_text__isnull=True)|
            models.Q(regulation_chunk__isnull=True,fda_reference__isnull=False,eu_text__isnull=True)|
            models.Q(regulation_chunk__isnull=True,fda_reference__isnull=True,eu_text__isnull=False)),name='search_passage_one_source')]


class SourceSearchEmbedding(models.Model):
    passage=models.ForeignKey(SourceSearchPassage,on_delete=models.CASCADE,related_name='embeddings')
    model_id=models.CharField(max_length=200)
    revision=models.CharField(max_length=40)
    profile=models.CharField(max_length=80)
    content_hash=models.CharField(max_length=64)
    vector=models.JSONField()
    dimension=models.PositiveIntegerField()
    indexed_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['passage','model_id','revision','profile'],name='source_embedding_identity')]


class EUSearchHead(models.Model):
    document=models.OneToOneField('EULegalDocument',on_delete=models.PROTECT,primary_key=True)
    active_text=models.ForeignKey(EULegalTextVersion,null=True,on_delete=models.PROTECT)
    published_at=models.DateTimeField(null=True)


class EUSearchRelease(AppendOnlyRecord):
    text_version=models.ForeignKey(EULegalTextVersion,on_delete=models.PROTECT)
    model_id=models.CharField(max_length=200)
    revision=models.CharField(max_length=40)
    profile=models.CharField(max_length=80)
    passage_count=models.PositiveIntegerField()
    published_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['text_version','model_id','revision','profile'],name='eu_search_release_identity')]


class EUSourceAttempt(AppendOnlyRecord):
    document=models.ForeignKey('EULegalDocument',on_delete=models.PROTECT,related_name='source_attempts')
    actor=models.ForeignKey('auth.User',on_delete=models.PROTECT)
    text_version=models.ForeignKey(EULegalTextVersion,null=True,on_delete=models.PROTECT)
    run_id=models.UUIDField()
    attempted_at=models.DateTimeField(auto_now_add=True)
    method=models.CharField(max_length=30)
    url=models.URLField(max_length=1500)
    resolved_url=models.URLField(max_length=1500,blank=True)
    status=models.CharField(max_length=40)
    http_status=models.PositiveIntegerField(null=True)
    attempt=models.PositiveIntegerField(default=1)
    wait_seconds=models.FloatField(default=0)
    detail=models.CharField(max_length=500,blank=True)
    original_hash=models.CharField(max_length=64,blank=True)


class SourceIndexBuild(models.Model):
    actor=models.ForeignKey('auth.User',on_delete=models.PROTECT)
    started_at=models.DateTimeField(auto_now_add=True)
    finished_at=models.DateTimeField(null=True)
    state=models.CharField(max_length=20,default='RUNNING')
    counts=models.JSONField(default=dict)
    failure=models.CharField(max_length=300,blank=True)


class SourceSearchExecution(AppendOnlyRecord):
    actor=models.ForeignKey('auth.User',on_delete=models.PROTECT)
    recorded_at=models.DateTimeField(auto_now_add=True)
    query_hash=models.CharField(max_length=64)
    filters=models.JSONField()
    snapshot=models.JSONField()


class SearchEvidenceAdoption(AppendOnlyRecord):
    execution=models.ForeignKey(SourceSearchExecution,on_delete=models.PROTECT,related_name='adoptions')
    actor=models.ForeignKey('auth.User',on_delete=models.PROTECT)
    recorded_at=models.DateTimeField(auto_now_add=True)
    draft=models.ForeignKey('DentalDraft',null=True,on_delete=models.PROTECT,related_name='search_adoptions')
    review=models.ForeignKey('MarketComparisonReview',null=True,on_delete=models.PROTECT,related_name='search_adoptions')
    snapshot=models.JSONField()
    rationale=models.CharField(max_length=2000)
    dedupe_key=models.CharField(max_length=64,unique=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=(models.Q(draft__isnull=False,review__isnull=True)|models.Q(draft__isnull=True,review__isnull=False)),name='search_adoption_one_target')]
