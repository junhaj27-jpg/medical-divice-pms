"""Operational RA records linked to the existing approval and evidence services."""
from django.db import models
from . import ra_models as ra

def ref(model, optional=False):
    return models.ForeignKey(model, on_delete=models.PROTECT, blank=optional, null=optional, related_name='+')

class QualityDocument(ra.ScopedRecord):
    document = ref(ra.ControlledDocument)
    parent = ref('self', True)
    department = models.CharField(max_length=120)
    level = models.CharField(max_length=12, choices=[(x,x) for x in ('MANUAL','PROCEDURE','INSTRUCTION','FORM')])
    requirements = models.ManyToManyField(ra.RARequirement, blank=True)
    training = ref(ra.TrainingRequirement, True)
    required_fields = models.JSONField(default=list, blank=True)
    template_approved = models.BooleanField(default=False)
    template_source = ref(ra.ControlledDocument, True)

    class Meta(ra.ScopedRecord.Meta):
        constraints = ra.ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=['document'], name='one_quality_document_version')]

class QualityRecord(ra.ScopedRecord):
    form_version = ref(QualityDocument)
    project = ref('pms.DHFProject', True)
    lot = ref('pms.ProductLot', True)
    change = ref(ra.ProductChange, True)
    training = ref(ra.TrainingAssignment, True)
    capa = ref('pms.CAPA', True)
    due_on = models.DateField(null=True, blank=True)
    record_key = models.CharField(max_length=100)
    values = models.JSONField(default=dict, blank=True)
    corrects = ref('self', True)
    class Meta(ra.ScopedRecord.Meta):
        constraints = ra.ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=['profile','record_key'], name='unique_quality_record_key')]

class QualityValidation(ra.ScopedRecord):
    system_version = models.CharField(max_length=100)
    intended_use = models.TextField()
    quality_impact = models.TextField()
    plan = models.TextField()
    acceptance = models.TextField()
    report = models.TextField(blank=True)
    supplier_material = ref(ra.SupplierMaterial, True)
    internal_confirmation = models.TextField(blank=True)
    previous = ref('self', True)
    revalidation_reason = models.TextField(blank=True)

class ValidationRequirement(ra.ScopedRecord):
    validation = ref(QualityValidation)
    requirement = models.TextField()
    risk = models.TextField()
    control = models.TextField()

class ValidationCase(ra.ScopedRecord):
    requirement = ref(ValidationRequirement)
    version = models.PositiveIntegerField(default=1)
    procedure = models.TextField()
    expected = models.TextField()
    previous = ref('self', True)

    class Meta(ra.ScopedRecord.Meta):
        constraints = ra.ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=['requirement', 'version'], name='unique_validation_case_version')]

class ValidationRun(ra.ScopedRecord):
    case = ref(ValidationCase)
    outcome = models.CharField(max_length=8, choices=[(x,x) for x in ('PASS','FAIL','WAIVED')])
    result = models.TextField()
    deviation = models.TextField(blank=True)
    retest_of = ref('self', True)

class DHFProject(ra.ScopedRecord):
    release = ref(ra.ProductRevision)
    purpose = models.TextField()

class DesignTrace(ra.ScopedRecord):
    project = ref(DHFProject)
    requirement = ref(ra.RARequirement, True)
    output = ref(ra.ControlledDocument, True)
    risk = ref(ra.ProductRisk, True)
    verification = ref(ra.ControlledDocument, True)
    change = ref(ra.ProductChange, True)
    release_review = ref(ra.ProductRevision, True)

class MeetingSource(ra.ScopedRecord):
    project = ref(DHFProject)
    minutes = ref('pms.Attachment')
    meeting_on = models.DateField()

    class Meta(ra.ScopedRecord.Meta):
        constraints = ra.ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=['project', 'minutes'], name='unique_dhf_meeting_source')]

class MeetingCandidate(ra.ScopedRecord):
    meeting = ref(MeetingSource)
    line_number = models.PositiveIntegerField()
    excerpt = models.TextField()
    category = models.CharField(max_length=40)
    document = ref(ra.ControlledDocument, True)
    mentioned_file = ref('pms.Attachment', True)
    suggested_owner = models.CharField(max_length=150, blank=True)
    suggested_due = models.CharField(max_length=30, blank=True)
    uncertainty = models.TextField(blank=True)
    confirmed_trace = ref(DesignTrace, True)
    class Meta(ra.ScopedRecord.Meta):
        constraints = ra.ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=['meeting','line_number'], name='unique_meeting_candidate_line')]

class DHFBaseline(ra.ScopedRecord):
    project = ref(DHFProject)
    baseline = models.JSONField(default=dict, blank=True)

class SoftwareChangeReview(ra.ScopedRecord):
    change = ref(ra.ProductChange)
    project = ref(DHFProject)
    classification = models.CharField(max_length=120, default='확인 필요')
    classification_basis = models.TextField(blank=True)
    function_comparison = models.TextField()
    algorithm_comparison = models.TextField()
    intended_use_comparison = models.TextField()
    package = ref(ra.SubmissionPackage, True)
    submission_manifest = models.JSONField(default=dict, blank=True)

class TechnicalSection(ra.ScopedRecord):
    review = ref(SoftwareChangeReview)
    section = models.CharField(max_length=120)
    document = ref(ra.ControlledDocument, True)
    readiness = models.CharField(max_length=12, choices=[(x,x) for x in ('MISSING','DRAFT','READY')], default='MISSING')

    class Meta(ra.ScopedRecord.Meta):
        constraints = ra.ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=['review', 'section'], name='unique_review_section')]

class ReviewResponse(ra.ScopedRecord):
    review = ref(SoftwareChangeReview)
    question = models.TextField()
    response = models.TextField(blank=True)
    package = ref(ra.SubmissionPackage, True)
    previous = ref('self', True)

class SecurityInventory(ra.ScopedRecord):
    release = ref(ra.ProductRevision)
    sbom = ref('pms.Attachment', True)
    assets = models.TextField(blank=True)
    interfaces = models.TextField(blank=True)
    components = models.JSONField(default=list, blank=True)

class SecurityFinding(ra.ScopedRecord):
    inventory = ref(SecurityInventory)
    identifier = models.CharField(max_length=120)
    source = models.CharField(max_length=500)
    checked_on = models.DateField()
    threat = models.TextField()
    impact = models.TextField()
    assessment = models.TextField()
    score_source_version = models.CharField(max_length=200, blank=True)
    score_as_reported = models.CharField(max_length=80, blank=True)
    due_on = models.DateField(null=True, blank=True)
    patch = models.TextField(blank=True)
    residual = models.TextField(blank=True)
    risk = ref(ra.ProductRisk, True)
    change = ref(ra.ProductChange, True)
    capa = ref('pms.CAPA', True)
    action = ref(ra.FieldSafetyAction, True)

class SecurityReview(ra.ScopedRecord):
    inventory = ref(SecurityInventory)
    test_plan = models.TextField()
    test_results = models.TextField(blank=True)
    open_items = models.TextField(blank=True)
    residual_decision = models.TextField(blank=True)
