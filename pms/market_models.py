"""Country registrations and vigilance records layered over the existing PMS history."""
from django.conf import settings
from django.db import models

from .history import AppendOnlyRecord

USER = settings.AUTH_USER_MODEL
LANGUAGES = [(code, name) for code, name in (
    ("ko-KR", "한국어"), ("en", "English"), ("de-DE", "Deutsch"),
    ("fr-FR", "Français"), ("es-ES", "Español"), ("it-IT", "Italiano"),
)]
COUNTRIES = ("KR", "US", "DE", "FR", "ES", "IT")
EU_COUNTRIES = ("DE", "FR", "ES", "IT")
MARKETS = [(code, code) for code in (*COUNTRIES, "XX")]
EVIDENCE_SCOPES = [*MARKETS[:-1], ("EU", "EU")]
UNSET = "UNKNOWN"
NA = "NA"


class MarketAccess(models.Model):
    """Presence of a scope restricts a user even when all grants are revoked."""
    user = models.OneToOneField(USER, on_delete=models.CASCADE, related_name="market_access")
    markets = models.JSONField(default=list, blank=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if not isinstance(self.markets, list) or any(code not in COUNTRIES for code in self.markets):
            raise ValidationError({"markets": "Use a list of country codes: KR, US, DE, FR, ES, IT."})

    def __str__(self):
        return str(self.user)


class ProductMarket(models.Model):
    device = models.ForeignKey("pms.MedicalDevice", on_delete=models.PROTECT, related_name="sales_markets")
    market = models.CharField(max_length=2, choices=MARKETS)
    pathway = models.CharField(max_length=180, blank=True)
    classification = models.CharField(max_length=180, blank=True)
    identifier = models.CharField(max_length=180, blank=True)
    status = models.CharField(max_length=16, default=UNSET, choices=[
        (v, v) for v in (UNSET, NA, "PREPARATION", "IN_REVIEW", "REGISTERED", "EXPIRED")
    ])
    owner = models.ForeignKey(USER, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    effective_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    submissions = models.TextField(blank=True)
    rationale = models.TextField(blank=True)
    authority = models.CharField(max_length=200, blank=True)
    submission_language = models.CharField(max_length=8, choices=[*LANGUAGES, (NA, NA)], blank=True)
    na_fields = models.JSONField(default=list, blank=True)
    eu_assessment = models.CharField(max_length=16, default=UNSET, choices=[
        (v, v) for v in (UNSET, NA, "ALIGNED", "CONFLICT")
    ])
    eu_rationale = models.TextField(blank=True)
    eu_versions = models.JSONField(default=list, blank=True)
    is_example = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["device", "market"], name="product_country_unique"),
                       models.CheckConstraint(condition=models.Q(effective_on__lte=models.F("expires_on")) |
                                              models.Q(effective_on__isnull=True) | models.Q(expires_on__isnull=True),
                                              name="market_registration_date_order")]


class MarketEvidence(AppendOnlyRecord):
    device = models.ForeignKey("pms.MedicalDevice", on_delete=models.PROTECT, related_name="market_evidence")
    scope = models.CharField(max_length=2, choices=EVIDENCE_SCOPES)
    regulation_document = models.ForeignKey("pms.RegulationDocument", on_delete=models.PROTECT,
                                            null=True, blank=True, related_name="market_source_versions")
    reference_key = models.SlugField(max_length=60)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=240)
    clause = models.CharField(max_length=240, blank=True)
    language = models.CharField(max_length=8, choices=LANGUAGES)
    official_url = models.URLField(max_length=1000, blank=True)
    excerpt = models.TextField()
    checked_on = models.DateField(null=True, blank=True)
    reviewer = models.ForeignKey(USER, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    is_example = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["device", "scope", "reference_key", "version"],
                                               name="market_evidence_version_unique")]


class MarketTranslation(AppendOnlyRecord):
    original = models.ForeignKey(MarketEvidence, on_delete=models.PROTECT, related_name="translations")
    language = models.CharField(max_length=8, choices=LANGUAGES)
    version = models.PositiveIntegerField()
    text = models.TextField()
    reviewer = models.ForeignKey(USER, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reviewed_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["original", "language", "version"],
                                               name="market_translation_version_unique")]


class CaseMarket(models.Model):
    complaint = models.ForeignKey("pms.CustomerComplaint", on_delete=models.PROTECT, related_name="market_cases")
    market = models.CharField(max_length=2, choices=MARKETS)
    owner = models.ForeignKey(USER, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    report_language = models.CharField(max_length=8, choices=LANGUAGES, default="en")
    occurred_at_source = models.CharField(max_length=50, blank=True)
    reported_at_source = models.CharField(max_length=50, blank=True)
    aware_at_source = models.CharField(max_length=50, blank=True)
    custom_at_source = models.CharField(max_length=50, blank=True)
    manual_decision = models.CharField(max_length=16, default="HOLD", choices=[
        (v, v) for v in ("HOLD", "REPORT", "NO_REPORT")
    ])
    manual_due_on = models.DateField(null=True, blank=True)
    reviewed = models.BooleanField(default=False)
    rationale = models.TextField(blank=True)
    legacy_application = models.ForeignKey("pms.RuleApplication", on_delete=models.PROTECT,
                                           null=True, blank=True, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["complaint", "market"], name="complaint_country_unique")]


class MarketAssessment(AppendOnlyRecord):
    case_market = models.ForeignKey(CaseMarket, on_delete=models.PROTECT, related_name="assessments")
    rule = models.ForeignKey("pms.ReportingRule", on_delete=models.PROTECT, null=True, blank=True)
    actor = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField(auto_now_add=True)
    snapshot = models.JSONField()

    class Meta:
        ordering = ("-pk",)


class MarketComparisonRun(AppendOnlyRecord):
    market = models.CharField(max_length=2, choices=MARKETS)
    baseline = models.ForeignKey("pms.ReportingRule", on_delete=models.PROTECT, related_name="+")
    proposed = models.ForeignKey("pms.ReportingRule", on_delete=models.PROTECT, related_name="+")
    actor = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField(auto_now_add=True)
    rules = models.JSONField()

    class Meta:
        ordering = ("-pk",)
        indexes = [models.Index(fields=("market", "actor", "-id"), name="market_comparison_lookup")]


class MarketComparisonResult(AppendOnlyRecord):
    run = models.ForeignKey(MarketComparisonRun, on_delete=models.PROTECT, related_name="results")
    entry = models.ForeignKey(CaseMarket, on_delete=models.PROTECT, related_name="comparisons")
    snapshot = models.JSONField()

    class Meta:
        ordering = ("pk",)
        constraints = [models.UniqueConstraint(fields=("run", "entry"), name="market_comparison_entry_unique")]


class MarketComparisonReview(AppendOnlyRecord):
    result = models.ForeignKey(MarketComparisonResult, on_delete=models.PROTECT, related_name="reviews")
    actor = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField(auto_now_add=True)
    complete = models.BooleanField()
    note = models.CharField(max_length=2000)

    class Meta:
        ordering = ("-pk",)
