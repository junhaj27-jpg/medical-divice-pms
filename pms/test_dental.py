from unittest.mock import patch
from zipfile import ZipFile
import io
import os
import hashlib
from pathlib import Path
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .dental_models import DentalProject
from .market_models import MarketAccess, ProductMarket
from .models import Attachment, BusinessPartner, ControlledDocument, Manufacturer, MedicalDevice, Profile, RegulatoryProfile
from .ra_services import save_record


class DentalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("demo-ra")
        Profile.objects.create(user=self.user, role="RA_QA")
        self.access = MarketAccess.objects.create(user=self.user, markets=["US"])
        manufacturer = Manufacturer.objects.create(name="DEMO-Manufacturer")
        self.device = MedicalDevice.objects.create(name="DEMO-Light", model_number="DEMO-01", manufacturer=manufacturer)
        ProductMarket.objects.create(device=self.device, market="US", is_example=True)
        organization = BusinessPartner.objects.create(name="DEMO-Organization")
        self.profile = save_record(RegulatoryProfile(), self.user, dict(
            device=self.device, jurisdiction="US", organization=organization, organization_role="MANUFACTURER",
            title="DEMO US", owner=self.user, is_example=True,
        ), "Example")
        self.client.force_login(self.user)
        self.url = reverse("market-dental", args=[self.device.pk])
        self.spec = {"action": "project", "product_name": "DEMO-Light", "model": "DEMO-01",
                     "intended_use": "Photopolymerization of restorative resin", "product_code": "EBZ",
                     "regulation": "872.6070", "use_scope": "restorative", "light_source": "broad_beam",
                     "scope_confirmed": "on", "example": "on", "power": "100"}

    def document(self, version=1, previous=None):
        content = b"DEMO-01 DEMO-02 High configured room bench method threshold result 120 mW. Optical test data."
        folder = Path.cwd() / f"dental-test-{uuid4().hex}"
        folder.mkdir()
        self.addCleanup(folder.rmdir)
        self.enterContext(override_settings(MEDIA_ROOT=folder))
        file = folder / "demo.txt"
        self.addCleanup(file.unlink, missing_ok=True)
        file.write_bytes(content)
        attachment = Attachment.objects.create(ra_profile=self.profile, uploaded_by=self.user, file="demo.txt",
                                               scan_status="PASSED", sha256=hashlib.sha256(content).hexdigest())
        return save_record(ControlledDocument(), self.user, dict(
            profile=self.profile, title="DEMO-Test", owner=self.user, is_example=True, category="TECHNICAL",
            number="DEMO-TR", version=version, primary_file=attachment, supersedes=previous, change_reason="Demo",
        ), "Example")

    def test_scope_and_missing_performance(self):
        dashboard = self.client.get(reverse("market-dashboard"), {"market": "US"})
        self.assertContains(dashboard, self.url)
        self.assertContains(dashboard, "Dental Curing Light 510(k)")
        registration = reverse("market-registration", args=[self.device.pk, "US"])
        self.assertContains(self.client.get(registration), self.url)
        for changes in ({"light_source": "laser"}, {"use_scope": "bleaching"}, {"product_code": "QNF"}):
            self.assertEqual(self.client.post(self.url, {**self.spec, **changes}).status_code, 302)
            self.assertEqual(self.client.post(self.url, {"action": "generate"}).status_code, 400)
        self.client.post(self.url, self.spec)
        response = self.client.get(self.url)
        self.assertContains(response, "방사 출력 시험 자료 필요")
        self.assertContains(response, "발열 시험 자료 필요")
        self.assertEqual(self.client.post(self.url, {"action": "na", "section": "III.I"}).status_code, 400)

    @patch("pms.dental_views.safe_attachment_bytes")
    def test_evidence_export_review_and_revisions(self, read):
        read.return_value = b"DEMO-01 High configured room bench method threshold result 120 mW. Optical test data."
        self.client.post(self.url, self.spec)
        doc = self.document()
        payload = {"action": "evidence", "section": "III.J.1", "document": doc.pk, "page": 1,
                   "excerpt": "Optical test data.", "model": "DEMO-02", "metric": "radiant_power",
                   "value": "120", "unit": "mW", "configuration": "configured", "mode": "High",
                   "conditions": "room", "method": "bench method", "acceptance": "threshold", "result": "result"}
        self.assertContains(self.client.post(self.url, {**payload, "excerpt": "Invented citation"}),
                            "발췌문을 확인할 수 없습니다", status_code=400)
        read.return_value += b" DEMO-02"
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        page = self.client.get(self.url)
        self.assertContains(page, "시험·자료 모델 불일치")
        self.assertContains(page, "값 충돌 확인")
        self.assertEqual(self.client.post(self.url, {**payload, "section": "III.A", "model": "DEMO-01",
                                                     "metric": "", "value": "", "unit": ""}).status_code, 302)
        self.assertEqual(self.client.post(self.url, {"action": "predicate", "k_number": "DEMO-PRED"}).status_code, 302)
        self.assertEqual(self.client.post(self.url, {"action": "generate"}).status_code, 302)
        project = DentalProject.objects.get()
        draft = project.drafts.get()
        export = lambda kind: reverse("market-dental-output", args=[self.device.pk, draft.pk, kind])
        docx = b"".join(self.client.get(export("docx")).streaming_content)
        with ZipFile(io.BytesIO(docx)) as file:
            xml = file.read("word/document.xml").decode()
        self.assertIn("Draft for RA Review", xml)
        self.assertIn("DEMO", xml)
        self.assertIn("https://www.fda.gov/media/74206/download", xml)
        self.assertEqual(xml.count("Optical test data. [DEMO-TR v1 / p.1]"), 1)
        gaps = b"".join(self.client.get(export("gaps")).streaming_content).decode("utf-8-sig")
        self.assertIn("DEMO-TR v1 / p.1", gaps)
        self.assertIn("발열 시험 자료 필요", gaps)
        matrix_bytes = b"".join(self.client.get(export("matrix")).streaming_content)
        self.assertIn("Performance Testing", matrix_bytes.decode("utf-8-sig"))
        if output := os.environ.get("DENTAL_DEMO_OUTPUT"):
            folder = Path(output)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "DEMO-dental-draft.docx").write_bytes(docx)
            (folder / "DEMO-dental-matrix.csv").write_bytes(matrix_bytes)
            (folder / "DEMO-dental-gaps.csv").write_bytes(gaps.encode("utf-8-sig"))
        evidence_url = reverse("market-dental-evidence", args=[self.device.pk, doc.pk])
        self.assertEqual(self.client.get(evidence_url).status_code, 200)
        self.assertEqual(self.client.post(export("review"), {"note": "DEMO reviewed"}).status_code, 302)
        self.document(2, doc)
        self.assertContains(self.client.get(self.url), "재검토 필요")
        self.assertEqual(self.client.post(export("review"), {"note": "Stale"}).status_code, 400)
        MarketAccess.objects.filter(pk=self.access.pk).update(markets=["DE"])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(export("docx")).status_code, 404)
        self.assertEqual(self.client.get(evidence_url).status_code, 404)
