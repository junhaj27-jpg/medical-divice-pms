from django.conf import settings
from django.db import models
from .history import AppendOnlyRecord


class EULegalDocument(AppendOnlyRecord):
    identifier = models.CharField(max_length=500)
    celex = models.CharField(max_length=60, blank=True)
    official_url = models.URLField(max_length=1000)
    title = models.CharField(max_length=500)
    source_type = models.CharField(max_length=20, choices=[(v, v) for v in ("eu_law", "eu_guide", "eu_standard_oj")])
    kind = models.CharField(max_length=20, choices=[(v, v) for v in ("eu_oj", "eu_amendment", "eu_correction", "eu_consolidated")])
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="updates")
    oj_reference = models.CharField(max_length=200, blank=True)
    published_on = models.DateField(null=True, blank=True)
    effective_on = models.DateField(null=True, blank=True)
    applies_on = models.DateField(null=True, blank=True)
    language = models.CharField(max_length=2)
    checked_on = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-pk",)
        constraints = [models.UniqueConstraint(fields=("identifier", "language"), name="eu_document_language")]

    def __str__(self):
        return f"{self.celex or self.identifier} · {self.language} · {self.title}"


class EUProjectLaw(AppendOnlyRecord):
    project = models.ForeignKey("DentalProject", on_delete=models.PROTECT, related_name="legal_links")
    section = models.CharField(max_length=10)
    document = models.ForeignKey(EULegalDocument, on_delete=models.PROTECT, related_name="project_links")
    clause = models.CharField(max_length=240)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("project", "section", "document", "clause"), name="eu_project_clause")]


class EUApplicabilityReview(AppendOnlyRecord):
    link = models.ForeignKey(EUProjectLaw, on_delete=models.PROTECT, related_name="reviews")
    decision = models.CharField(max_length=20, choices=[(v, v) for v in ("eu_pending", "hs_applies", "hs_does_not_apply")])
    reason = models.TextField(max_length=2000)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-pk",)


class EUImpactConfirmation(AppendOnlyRecord):
    project = models.ForeignKey("DentalProject", on_delete=models.PROTECT, related_name="legal_impacts")
    section = models.CharField(max_length=10)
    document = models.ForeignKey(EULegalDocument, on_delete=models.PROTECT, related_name="confirmations")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(max_length=2000)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("project", "section", "document"), name="eu_confirmed_item")]
