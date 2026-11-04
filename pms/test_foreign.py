from datetime import timedelta
from shutil import rmtree
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from . import foreign
from .foreign_models import ForeignApplication
from .models import Attachment, BusinessPartner, RegulatoryProfile
from .ra_services import save_record
from .services import decide_approval
from .tests import Base


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ForeignTests(Base):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.org = BusinessPartner.objects.create(name="Test organization")
        self.us = self.application("US")
        self.eu = self.application("EU")
        self.media = settings.BASE_DIR / ".test-media" / uuid4().hex
        self.media.mkdir(parents=True)
        self.addCleanup(rmtree, self.media)
        override = override_settings(MEDIA_ROOT=self.media, ANTIVIRUS_COMMAND=["test-scanner"])
        override.enable()
        self.addCleanup(override.disable)

    def application(self, market):
        profile = save_record(RegulatoryProfile(), self.raqa, dict(
            device=self.d, jurisdiction=market, organization=self.org, organization_role="MANUFACTURER",
            title=market, owner=self.raqa, is_example=False,
        ), "Test scope")
        return foreign.save_application(self.raqa, dict(
            profile=profile, market=market, title=market + " case", kind="NEW", previous=None,
            model_scope=self.d.model_number, release=None, intended_use="Test use", classification="", pathway="",
            rationale="Classification under review", owner=self.raqa, target_on=self.today, is_example=False,
        ))

    def proof(self, case):
        from .file_security import scan_attachment
        file = Attachment(ra_profile=case.profile, original_name="fixture.txt", uploaded_by=self.raqa)
        file.file.save("fixture.txt", ContentFile(b"Fictional test evidence"), save=False)
        file.save()
        with patch("pms.file_security.subprocess.run") as scanner:
            scanner.return_value.returncode = 0
            scan_attachment(file, self.raqa)
        return file

    def prepare(self):
        proof = self.proof(self.us)
        for document in self.us.documents.all():
            foreign.save_document(self.raqa, self.us.pk, dict(
                title=document.title, owner=self.raqa, status="READY", version="1",
                applicability="APPLIES", rationale="Included in test", evidence=proof,
            ), document.pk)
        foreign.operate(self.raqa, self.us.pk, "review", {})
        self.raqa.profile.role = "ADMIN"
        self.raqa.profile.save()
        with self.assertRaisesMessage(ValidationError, "작성자와 최종 승인자를 분리"):
            foreign.operate(self.raqa, self.us.pk, "approve", {})
        self.raqa.profile.role = "RA_QA"
        self.raqa.profile.save()
        foreign.operate(self.admin, self.us.pk, "approve", {})
        return proof

    def test_market_scope_filters_and_direct_permissions(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("foreign-detail", args=[self.us.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("foreign-action", args=[self.us.pk, "review"])).status_code, 403)
        self.client.force_login(self.raqa)
        self.assertEqual(self.client.post(reverse("foreign-action", args=[self.us.pk, "approve"])).status_code, 403)
        listing = self.client.get(reverse("foreign-device", args=[self.d.pk]), {"market": "EU", "owner": self.raqa.pk, "stage": "PREPARATION"})
        self.assertContains(listing, self.eu.title)
        self.assertNotContains(listing, self.us.title)
        self.assertContains(self.client.get(reverse("foreign-detail", args=[self.us.pk])), "미확정")
        values = {field: getattr(self.us, field) for field in foreign.APP_FIELDS}
        values.update(title="US change", kind="CHANGE", previous=self.eu)
        with self.assertRaises(ValidationError):
            foreign.save_application(self.raqa, values)
        values["previous"] = self.us
        followup = foreign.save_application(self.raqa, values)
        self.assertEqual(followup.previous, self.us)
        self.assertEqual(self.client.get(reverse("foreign-edit", args=[followup.pk])).status_code, 200)
        with self.assertRaises(ValidationError):
            foreign.operate(self.raqa, self.eu.pk, "review", {})
        legacy = self.complaint()
        self.assertEqual(self.client.get(reverse("complaint-workspace", args=[legacy.pk])).status_code, 200)

    def test_stale_approval_submission_snapshot_and_repeated_supplements(self):
        proof = self.prepare()
        values = {field: getattr(self.us, field) for field in foreign.APP_FIELDS}
        values["intended_use"] = "Updated intended use"
        foreign.save_application(self.raqa, values, self.us.pk)
        self.assertTrue(foreign.approvals(self.us).first().superseded)
        values["intended_use"] = self.us.intended_use
        foreign.save_application(self.raqa, values, self.us.pk)
        submit = dict(submitted_on=self.today, reference="TEST-US-1", evidence=proof)
        with self.assertRaisesMessage(ValidationError, "현재 범위"):
            foreign.operate(self.raqa, self.us.pk, "submit", submit)
        foreign.operate(self.raqa, self.us.pk, "review", {})
        with self.assertRaises(ValidationError):
            decide_approval(foreign.approvals(self.us).first(), self.admin, "APPROVED")
        foreign.operate(self.admin, self.us.pk, "approve", {})
        self.client.force_login(self.raqa)
        url = reverse("foreign-action", args=[self.us.pk, "submit"])
        self.assertContains(self.client.post(url, {"submitted_on": self.today, "reference": "TEST-US-1"}), "필수")
        with self.assertRaises(ValidationError):
            foreign.operate(self.raqa, self.us.pk, "submit", {**submit, "evidence": self.proof(self.eu)})
        self.assertRedirects(self.client.post(url, {**submit, "evidence": proof.pk}), reverse("foreign-detail", args=[self.us.pk]))
        document = self.us.documents.order_by("pk").first()
        new = {field: getattr(document, field) for field in foreign.DOC_FIELDS}
        foreign.save_document(self.raqa, self.us.pk, {**new, "version": "2"}, document.pk)
        self.assertEqual(self.us.submissions.get().manifest["documents"][0]["version"], "1")
        supplement = dict(requested_on=self.today, due_on=self.today + timedelta(days=1), owner=self.raqa, basis="Internal demo deadline")
        for _ in range(2):
            foreign.operate(self.raqa, self.us.pk, "supplement", supplement)
        first, second = self.us.supplements.order_by("pk")
        result = dict(kind="Fictional outcome", issuer="Fictional reviewer", issued_on=self.today,
                      reference="TEST-RESULT", expires_on=None, evidence=proof)
        with self.assertRaises(ValidationError):
            foreign.operate(self.raqa, self.us.pk, "result", result)
        for request in (first, second):
            self.assertRedirects(self.client.post(reverse("foreign-respond", args=[self.us.pk, request.pk]), {
                "response": proof.pk, "responded_on": self.today,
            }), reverse("foreign-detail", args=[self.us.pk]))
        self.assertEqual(self.us.supplements.filter(task__status="DONE").count(), 2)
        foreign.operate(self.raqa, self.us.pk, "result", result)
        self.assertEqual(self.us.result.issuer, "Fictional reviewer")
        self.eu.refresh_from_db()
        self.assertEqual(self.eu.stage, ForeignApplication.Stage.PREPARATION)

    def test_seed_repeat(self):
        import os
        with patch.dict(os.environ, {"DEMO_PASSWORD": "fictional-password"}):
            call_command("seed_demo", verbosity=0)
        with patch("pms.file_security.subprocess.run") as scanner:
            scanner.return_value.returncode = 0
            for _ in range(2):
                call_command("seed_foreign_demo", verbosity=0)
        demo = ForeignApplication.objects.filter(is_example=True)
        self.assertEqual(demo.count(), 2)
        us = demo.get(market="US")
        self.assertEqual(us.submissions.count(), 1)
        self.assertEqual(us.supplements.count(), 2)
        self.assertEqual(us.supplements.filter(responded_on__isnull=False).count(), 1)
        self.assertFalse(hasattr(us, "result"))
        self.assertEqual(demo.get(market="EU").stage, "PREPARATION")

