from copy import deepcopy
from datetime import date
import io
from zipfile import ZipFile

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse

from .dental_models import DentalProject, WritingTemplate
from .dental_views import documents_for, references_for
from .dental_workflow import build_snapshot
from .market_models import MarketAccess, ProductMarket
from .models import MedicalDevice
from .test_dental import DentalTests


class WritingTests(DentalTests):
    def create_project(self, key, template=None):
        template = template or WritingTemplate.objects.get(key=key, version=1)
        url = reverse("market-writing", args=[self.device.pk])
        data = {**self.spec, "template_id": template.pk, "users": "Clinicians", "environment": "Clinic",
                "product_version": "DEMO-v1", "software": "DEMO-v1", "inputs": "EEG", "outputs": "Analysis",
                "measurements": "Pulse", "sensors": "Optical", "alarms": "Present"}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        return url, DentalProject.objects.get(device=self.device)

    def test_three_types_common_and_fourth_admin_template(self):
        section_sets = []
        for version, key in enumerate(("dental", "eeg", "monitor"), 1):
            DentalProject.objects.filter(device=self.device).delete()
            url, project = self.create_project(key)
            doc = self.document(version)
            section = project.template.items[0]["id"]
            response = self.client.post(url, {
                "action": "evidence", "section": section, "document": doc.pk, "page": 1,
                "model": "DEMO-01", "excerpt": "Optical test data.", "location": "DEMO Table 1",
            })
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.client.post(url, {"action": "generate"}).status_code, 302)
            draft = project.drafts.get()
            section_sets.append(set(row["section"] for row in draft.snapshot["rows"]))
            for kind in ("docx", "gaps", "matrix", "mapping"):
                response = self.client.get(reverse("market-dental-output", args=[self.device.pk, draft.pk, kind]))
                self.assertEqual(response.status_code, 200)
                content = b"".join(response.streaming_content)
                self.assertTrue(content)
                if kind == "docx":
                    xml = ZipFile(io.BytesIO(content)).read("word/document.xml").decode()
                    self.assertIn("Draft for RA Review", xml)
                    self.assertIn(project.template.name, xml)
                    self.assertIn("Optical test data.", xml)
            project.drafts.all().delete()
            project.evidence.all().delete()
            project.delete()
        self.assertEqual(len({frozenset(s) for s in section_sets}), 3)
        url, project = self.create_project("common")
        self.assertEqual(self.client.post(url, {"action": "generate"}).status_code, 400)

        admin_user = get_user_model().objects.create_superuser("template-admin")
        self.client.force_login(admin_user)
        payload = {
            "key": "fourth", "version": 1, "name": "DEMO Fourth type", "market": "US",
            "pathway": "RA verification required", "state": "DRAFT", "example": "on",
            "conditions": '{"include":"DEMO fourth"}', "fields": '{"signal":"Signal input"}',
            "items": '[{"id":"FOURTH","title":"Fourth evidence","condition":"always","evidence_type":"DEMO","source_section":"DEMO","page":0,"draft_section":"Fourth draft","mapping":"RA verification required"}]',
            "checked_on": "2026-11-14", "_save": "Save",
        }
        self.assertEqual(self.client.post("/admin/pms/writingtemplate/add/", payload).status_code, 302)
        template = WritingTemplate.objects.get(key="fourth")
        for state in ("REVIEW", "PUBLISHED"):
            payload["state"] = state
            self.assertEqual(self.client.post(f"/admin/pms/writingtemplate/{template.pk}/change/", payload).status_code, 302)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(url), "DEMO Fourth type")
        self.client.post(url, {"action": "template", "template_id": template.pk})
        self.assertContains(self.client.get(url), "Signal input")
        self.assertContains(self.client.get(url), "Fourth evidence")

    def test_revision_preserves_old_draft_and_changes_are_explicit(self):
        url, project = self.create_project("eeg")
        self.client.post(url, {"action": "generate"})
        draft = project.drafts.get()
        original = deepcopy(draft.snapshot)
        template = project.template
        user = get_user_model().objects.create_superuser("clone-admin")
        request = RequestFactory().post("/admin/")
        request.user = user
        from .writing_admin import WritingTemplateAdmin
        model_admin = WritingTemplateAdmin(WritingTemplate, admin.site)
        model_admin.clone_version(request, WritingTemplate.objects.filter(pk=template.pk))
        revision = WritingTemplate.objects.get(key="eeg", version=2)
        revision.items[0]["title"] = "Updated EEG evidence"
        revision.state = "REVIEW"
        revision.save()
        revision.state = "PUBLISHED"
        revision.save()
        self.assertContains(self.client.get(url), "EEG.IO")
        project.refresh_from_db()
        self.assertEqual(project.template_id, template.pk)
        self.client.post(url, {"action": "template", "template_id": revision.pk})
        self.assertContains(self.client.get(url), "Updated EEG evidence")
        project.refresh_from_db()
        self.assertFalse(project.specification["scope_confirmed"])
        draft.refresh_from_db()
        self.assertEqual(draft.snapshot, original)
        self.assertContains(self.client.get(url), "재검토 필요")
        self.assertEqual(self.client.get(reverse("market-dental-output", args=[self.device.pk, draft.pk, "docx"])).status_code, 200)
        with self.assertRaises(ValidationError):
            template.save()

    def test_other_project_documents_and_unconfirmed_scope_are_blocked(self):
        url, project = self.create_project("eeg")
        document = self.document()
        other = MedicalDevice.objects.create(manufacturer=self.device.manufacturer, name="DEMO Other", model_number="DEMO-OTHER")
        ProductMarket.objects.create(device=other, market="US", is_example=True)
        other_url = reverse("market-writing", args=[other.pk])
        data = {**self.spec, "template_id": project.template_id, "users": "Clinicians", "environment": "Clinic",
                "product_version": "DEMO-v1"}
        self.client.post(other_url, data)
        payload = {"action": "evidence", "document": document.pk, "section": "EEG.IO", "page": 1,
                   "excerpt": "Optical test data.", "model": "DEMO-01"}
        self.assertEqual(self.client.post(other_url, payload).status_code, 400)
        self.assertEqual(self.client.get(reverse("market-dental-evidence", args=[other.pk, document.pk])).status_code, 404)
        self.assertEqual(self.client.post(url, {**data, "scope_confirmed": ""}).status_code, 302)
        self.assertEqual(self.client.post(url, {"action": "generate"}).status_code, 400)
        MarketAccess.objects.filter(pk=self.access.pk).update(markets=["DE"])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_software_version_mismatch_is_a_gap(self):
        url, project = self.create_project("eeg")
        document = self.document()
        project.evidence.create(document=document, section="EEG.SW", details={
            "model": "DEMO-01", "software_version": "DEMO-v0", "metric": "", "value": "", "unit": "",
            "location": "Table 1", "page": 1, "excerpt": "Optical test data.",
            "configuration": "", "mode": "", "conditions": "", "method": "", "acceptance": "", "result": "",
            "identity": [document.revision, document.primary_file_id, document.primary_file.sha256],
        })
        snapshot = build_snapshot(project, references_for(project, documents_for(self.device)))
        row = next(row for row in snapshot["rows"] if row["section"] == "EEG.SW")
        self.assertIn("소프트웨어 버전 불일치: DEMO-v0", row["gaps"])
        self.assertFalse(row["selected"])
