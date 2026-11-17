from django.conf import settings
from django.db import models
from .history import AppendOnlyRecord


class MRIConfiguration(AppendOnlyRecord):
    device = models.ForeignKey("MedicalDevice", on_delete=models.PROTECT, related_name="mri_configurations")
    family = models.ForeignKey("MedicalDevice", on_delete=models.PROTECT, related_name="mri_family_configurations")
    version = models.PositiveIntegerField()
    configuration_name = models.CharField(max_length=160)
    intended_use = models.TextField(max_length=1500)
    target_population = models.CharField(max_length=400)
    users = models.CharField(max_length=400)
    environment = models.CharField(max_length=400)
    field_strength_t = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    magnet_type = models.CharField(max_length=100, blank=True)
    rf_coil = models.CharField(max_length=400, blank=True)
    modes = models.CharField(max_length=400, blank=True)
    accessories = models.TextField(max_length=2000, blank=True)
    software_version = models.CharField(max_length=100, blank=True)
    is_example = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-version", "-pk")
        constraints = [models.UniqueConstraint(fields=("device", "version"), name="mri_model_configuration_version")]


class MRIApplicabilityReview(AppendOnlyRecord):
    evidence = models.ForeignKey("DentalEvidence", on_delete=models.PROTECT, related_name="mri_reviews")
    configuration = models.ForeignKey(MRIConfiguration, on_delete=models.PROTECT)
    decision = models.CharField(max_length=10, choices=[("accept", "적용 근거 확인"), ("reject", "적용 불가")])
    rationale = models.TextField(max_length=2000)
    source_identity = models.JSONField()
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-pk",)
