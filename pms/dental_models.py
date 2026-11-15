from django.conf import settings
from django.db import models

from .history import AppendOnlyRecord
from django.core.exceptions import ValidationError
import re


class WritingTemplate(models.Model):
    key = models.SlugField()
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=200)
    market = models.CharField(max_length=2, default="US")
    pathway = models.CharField(max_length=80, default="RA verification required")
    state = models.CharField(max_length=12, choices=[(v, v) for v in ("DRAFT", "REVIEW", "PUBLISHED")], default="DRAFT")
    example = models.BooleanField(default=False)
    source_url = models.URLField(blank=True)
    issued_on = models.DateField(null=True, blank=True)
    checked_on = models.DateField(null=True, blank=True)
    conditions = models.JSONField(default=dict, blank=True)
    fields = models.JSONField(default=dict, blank=True)
    items = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("key", "version"), name="writing_template_version")]

    def __str__(self):
        return f"{self.name} v{self.version} ({self.state})"

    def clean(self):
        super().clean()
        if self.market not in ("US", "EU") or not isinstance(self.fields, dict) or not isinstance(self.conditions, dict):
            raise ValidationError("US/EU 템플릿의 fields/conditions는 JSON 객체입니다.")
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", k) or not isinstance(v, str) for k, v in self.fields.items()):
            raise ValidationError("필드 ID와 표시 이름을 확인하세요.")
        if set(self.fields) & {"template", "template_id", "not_applicable", "predicate", "predicate_confirmed", "action", "scope_confirmed", "example", "model", "product_name", "intended_use", "changed", "confirmed_pathway"}:
            raise ValidationError("시스템 필드를 템플릿 필드로 사용할 수 없습니다.")
        if any(not isinstance(self.conditions.get(key, []), list) or any(not isinstance(v, str) for v in self.conditions.get(key, []))
               for key in ("product_codes", "regulations")):
            raise ValidationError("제품 코드와 규정 번호 후보는 문자열 목록입니다.")
        if not isinstance(self.items, list) or not self.items:
            raise ValidationError("체크리스트가 필요합니다.")
        ids = set()
        for item in self.items:
            if (not isinstance(item, dict) or not {"id", "title", "condition", "evidence_type", "source_section", "page", "draft_section", "mapping"} <= item.keys()
                    or not isinstance(item["id"], str)
                    or not re.fullmatch(r"[A-Za-z0-9_.-]{1,10}", str(item["id"])) or item["id"] in ids
                    or type(item["page"]) is not int or item["page"] < 0
                    or any(not isinstance(item[k], str) for k in ("title", "condition", "evidence_type", "source_section", "draft_section", "mapping"))):
                raise ValidationError("항목 ID·조건·증빙 유형·출처 절/페이지·초안 섹션·매핑을 확인하세요.")
            ids.add(item["id"])
        if self.state == "PUBLISHED" and not self.checked_on:
            raise ValidationError("게시 전 확인일을 기록하세요.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.state == "PUBLISHED":
                raise ValidationError("게시 버전은 보존됩니다. 복제하여 개정하세요.")
            if self.state == "PUBLISHED" and old.state != "REVIEW":
                raise ValidationError("검토 상태를 거쳐 게시하세요.")
        elif self.state != "DRAFT":
            raise ValidationError("초안으로 등록하세요.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("템플릿 버전을 보존하세요.")


class DentalGuide(AppendOnlyRecord):
    issued_on = models.DateField(unique=True)
    status = models.CharField(max_length=20)
    url = models.URLField()
    checked_on = models.DateField()
    sha256 = models.CharField(max_length=64)
    sections = models.JSONField()


class DentalProject(models.Model):
    market = models.CharField(max_length=2, default="US", choices=[("US", "US"), ("EU", "EU")])
    template = models.ForeignKey(WritingTemplate, on_delete=models.PROTECT, null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    device = models.ForeignKey("MedicalDevice", on_delete=models.PROTECT, related_name="writing_projects")
    guide = models.ForeignKey(DentalGuide, on_delete=models.PROTECT)
    specification = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("device", "market"), name="writing_product_market")]


class DentalEvidence(AppendOnlyRecord):
    project = models.ForeignKey(DentalProject, on_delete=models.PROTECT, related_name="evidence")
    document = models.ForeignKey("ControlledDocument", on_delete=models.PROTECT)
    section = models.CharField(max_length=10)
    details = models.JSONField()


class DentalDraft(AppendOnlyRecord):
    project = models.ForeignKey(DentalProject, on_delete=models.PROTECT, related_name="drafts")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    snapshot = models.JSONField()


class DentalDraftReview(AppendOnlyRecord):
    draft = models.ForeignKey(DentalDraft, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(max_length=2000)
