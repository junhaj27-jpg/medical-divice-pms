import os
from pathlib import Path
from shutil import rmtree
from uuid import uuid4
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .file_security import scan_attachment
from .models import Attachment, CAPA, CustomerComplaint, MedicalDevice, RegulatoryReport, SoftwareRelease, UDI
from .reporting import generate_report
from .services import decide_approval, latest_complaint_approval, request_complaint_approval, transition_complaint
from .tests import Base
from .workflow import evaluate_capa


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SoftwareTrackingTests(Base):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.software = MedicalDevice.objects.create(
            manufacturer=self.d.manufacturer, name="EEG software", model_number="EEG-SW", product_type="SOFTWARE",
        )
        self.udi_sw = UDI.objects.create(device=self.software, device_identifier="EEG-SW-UDI")
        self.release = SoftwareRelease.objects.create(device=self.software, version="v1.2.0", released_on=self.today)
        self.fixed = SoftwareRelease.objects.create(device=self.software, version="v1.2.1", released_on=self.today)
        other = MedicalDevice.objects.create(
            manufacturer=self.d.manufacturer, name="Other software", model_number="OTHER-SW", product_type="SOFTWARE",
        )
        self.other = SoftwareRelease.objects.create(device=other, version="v9.0.0", released_on=self.today)

    def intake(self, title, release=""):
        return self.client.post(reverse("complaint-create"), {
            "device": self.software.pk, "udi": self.udi_sw.pk, "intake_release": release,
            "complaint_type": "DELAY", "title": title, "description": "가상 결과 지연",
            "occurred_on": self.today, "reported_on": self.today,
        })

    def test_intake_filters_and_legacy_lot_flow(self):
        legacy = self.complaint()
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("complaint-workspace", args=[legacy.pk])), self.lot.lot_number)
        self.client.force_login(self.raqa)
        self.assertContains(self.client.get(reverse("lot-detail", args=[self.lot.pk])), self.lot.lot_number)
        response = self.client.post(reverse("lot-create"), {
            "device": self.d.pk, "udi": self.udi.pk, "lot_number": "EEG-LOT-NEW",
            "distributed_quantity": 5,
        })
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.intake("unknown").status_code, 302)
        self.assertEqual(self.intake("known", self.release.pk).status_code, 302)
        self.assertEqual(self.intake("wrong product", self.other.pk).status_code, 200)
        self.assertFalse(CustomerComplaint.objects.filter(title="wrong product").exists())
        unknown = CustomerComplaint.objects.get(title="unknown")
        self.assertIsNone(unknown.intake_release_id)
        self.assertIsNone(legacy.intake_release_id)
        self.assertContains(self.client.get(reverse("complaint-workspace", args=[unknown.pk])), "버전 미확인")
        url = reverse("complaint-list")
        self.assertEqual(list(self.client.get(url, {"unknown": "1"}).context["items"]), [unknown])
        self.assertEqual(self.client.get(url, {"device": self.software.pk}).context["items"].count(), 2)
        self.assertEqual(self.client.get(url, {"release": self.release.pk}).context["items"].get().title, "known")
        versions = self.client.get(reverse("device-releases", args=[self.software.pk])).json()
        self.assertEqual({item["id"] for item in versions}, {self.release.pk, self.fixed.pk})

    def test_scope_permissions_and_duplicate_release(self):
        self.client.force_login(self.staff)
        self.intake("scope", self.release.pk)
        case = CustomerComplaint.objects.get(title="scope")
        url = reverse("software-impact-save", args=[case.pk])
        release_url = reverse("release-create", args=[self.software.pk])
        self.assertEqual(self.client.post(url, {"affected_releases": [self.release.pk]}).status_code, 302)
        self.assertEqual(self.client.post(release_url, {"version": "v2.0.0", "released_on": self.today}).status_code, 302)
        self.assertFalse(case.affected_releases.exists())
        self.assertFalse(self.software.software_releases.filter(version="v2.0.0").exists())
        self.client.force_login(self.raqa)
        self.client.post(url, {"affected_releases": [self.other.pk]})
        self.assertFalse(case.affected_releases.exists())
        with self.assertRaises(ValidationError), transaction.atomic():
            case.affected_releases.add(self.other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SoftwareRelease.objects.create(device=self.software, version=self.release.version, released_on=self.today)
        self.assertContains(self.client.post(release_url, {
            "version": self.release.version, "released_on": self.today,
        }), "이미 등록된 제품 버전")
        self.assertEqual(self.client.post(release_url, {"version": "v2.0.0", "released_on": self.today}).status_code, 302)

    def test_verification_snapshot_and_reapproval(self):
        self.client.force_login(self.staff)
        self.intake("approval", self.release.pk)
        case = CustomerComplaint.objects.get(title="approval")
        case.status = "APPROVAL"
        case.save()
        capa = CAPA.objects.create(complaint=case, title="CAPA", owner=self.raqa, due_date=self.today, corrective_action="UI update")
        data = dict(fixed_release=self.other, action_result="Updated", criteria="Within 2 seconds",
                    scheduled_on=self.today, evaluated_on=self.today, verdict="PASS", rationale="30 trials")
        with self.assertRaisesMessage(ValidationError, "수정 릴리스는 사건 제품에 속해야"):
            evaluate_capa(capa, self.raqa, data)
        first = request_complaint_approval(case, self.raqa)
        decide_approval(first, self.admin, "APPROVED")
        transition_complaint(case, "ACTION_COMPLETE", self.admin)
        case.affected_releases.add(self.release)
        with self.assertRaisesMessage(ValidationError, "재승인"):
            transition_complaint(case, "CLOSED", self.admin)
        self.client.force_login(self.raqa)
        workspace = reverse("complaint-workspace", args=[case.pk])
        self.assertContains(self.client.get(workspace), 'id="reapproval-reason"')
        self.assertRedirects(self.client.post(reverse("approval-request", args=[case.pk]), {
            "reason": "영향 범위 변경",
        }), workspace)
        pending = latest_complaint_approval(case)
        self.assertEqual(pending.snapshot["request_reason"], "영향 범위 변경")
        media = settings.BASE_DIR / ".test-media" / uuid4().hex
        media.mkdir(parents=True)
        self.addCleanup(rmtree, media)
        with override_settings(MEDIA_ROOT=media, ANTIVIRUS_COMMAND=["scanner"]):
            evidence = Attachment(complaint=case, uploaded_by=self.raqa, original_name="verification.txt")
            evidence.file.save("verification.txt", ContentFile(b"Fictional verification: 30 successful trials."))
            with patch("pms.file_security.subprocess.run") as scanner:
                scanner.return_value.returncode = 0
                scan_attachment(evidence, self.raqa)
            evaluation = evaluate_capa(capa, self.raqa, dict(data, fixed_release=self.fixed), [evidence])
            self.assertEqual(evaluation.evidence.get(), evidence)
            with self.assertRaisesMessage(ValidationError, "재승인"):
                decide_approval(pending, self.admin, "APPROVED")
            updated = request_complaint_approval(case, self.raqa, reason="수정 검증 반영")
            decide_approval(updated, self.admin, "APPROVED")
            transition_complaint(case, "ACTION_COMPLETE", self.admin)
            transition_complaint(case, "CLOSED", self.admin)
            self.client.force_login(self.raqa)
            report = RegulatoryReport.objects.create(complaint=case, document_number="DEMO-SW-TEST", author=self.raqa)
            response = self.client.get(reverse("report-print", args=[report.pk]))
            self.assertContains(response, "v1.2.1")
            self.assertContains(response, "verification.txt")
            if os.environ.get("PDF_KOREAN_FONT"):
                artifact = generate_report(case, self.raqa)
                original = Path(artifact.file.path).read_bytes()
                case.impact_rationale = "Later review"
                case.save()
                revised = generate_report(case, self.raqa)
                artifact.refresh_from_db()
                self.assertEqual(artifact.snapshot["software"]["rationale"], "")
                self.assertEqual(revised.snapshot["software"]["rationale"], "Later review")
                self.assertEqual(Path(artifact.file.path).read_bytes(), original)
