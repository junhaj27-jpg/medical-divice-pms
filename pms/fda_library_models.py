from django.conf import settings
from django.db import models
from .history import AppendOnlyRecord


class FDAReferenceVersion(AppendOnlyRecord):
    key = models.SlugField(max_length=100)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    source_type = models.CharField(max_length=20, choices=[(v, v) for v in ("classification", "regulation", "guidance", "standard")])
    document_version = models.CharField(max_length=160)
    issued_on = models.DateField(null=True, blank=True)
    revised_on = models.DateField(null=True, blank=True)
    checked_on = models.DateField()
    official_url = models.URLField(max_length=1000)
    pdf_url = models.URLField(max_length=1000, blank=True)
    scope = models.TextField(max_length=4000)
    device_types = models.JSONField(default=list)
    sections = models.JSONField(default=list)
    pages = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64)
    retrieval_status = models.CharField(max_length=30)
    failure_reason = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="revisions")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("key", "-version")
        constraints = [models.UniqueConstraint(fields=("key", "version"), name="fda_reference_version"),
                       models.UniqueConstraint(fields=("key", "content_hash"), name="fda_reference_content")]

    def __str__(self):
        return f"{self.title} · {self.document_version} · v{self.version}"


class ProjectFDAReference(AppendOnlyRecord):
    project = models.ForeignKey("DentalProject", on_delete=models.PROTECT, related_name="fda_references")
    source = models.ForeignKey(FDAReferenceVersion, on_delete=models.PROTECT, related_name="project_links")
    product_evidence = models.ForeignKey("MarketEvidence", on_delete=models.PROTECT)
    section = models.CharField(max_length=10)
    clause = models.CharField(max_length=240)
    page = models.PositiveIntegerField(default=0)
    rationale = models.TextField(max_length=2000)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("project", "source", "section", "clause", "page"), name="project_fda_citation")]
