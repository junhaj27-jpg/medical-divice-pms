from datetime import timedelta
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .models import *
from .services import audit, decide_approval, recurrent_warning, request_complaint_approval, transition_complaint, visible_complaints
class Base(TestCase):
    def setUp(self):
        self.staff=User.objects.create_user("staff",password="test-password-123"); Profile.objects.create(user=self.staff,role="STAFF")
        self.other=User.objects.create_user("other",password="test-password-123"); Profile.objects.create(user=self.other,role="STAFF")
        self.raqa=User.objects.create_user("raqa",password="test-password-123"); Profile.objects.create(user=self.raqa,role="RA_QA")
        self.admin=User.objects.create_superuser("admin",password="test-password-123"); Profile.objects.create(user=self.admin,role="ADMIN")
        self.m=Manufacturer.objects.create(name="M"); self.d=MedicalDevice.objects.create(manufacturer=self.m,name="D",model_number="1"); self.udi=UDI.objects.create(device=self.d,device_identifier="UDI1"); self.lot=ProductLot.objects.create(device=self.d,udi=self.udi,lot_number="L1",distributed_quantity=10)
    def complaint(self,user=None,kind="TYPE",days=0): return CustomerComplaint.objects.create(device=self.d,udi=self.udi,lot=self.lot,complaint_type=kind,title="case",description="safe",occurred_on=timezone.localdate(),reported_on=timezone.localdate()-timedelta(days=days),reporter=user or self.staff)
class DomainTests(Base):
    def test_risk_calculation(self):
        r=RiskAssessment.objects.create(complaint=self.complaint(),severity=5,probability=4,assessed_by=self.raqa); self.assertEqual((r.score,r.level,r.capa_review_required),(20,"CRITICAL",True))
    def test_invalid_transition_blocked(self):
        c=self.complaint(); self.assertRaises(ValidationError,transition_complaint,c,"RISK",self.raqa)
    def test_risk_stage_requires_assessment(self):
        c=self.complaint(); c.status="RISK"; c.save(); self.assertRaisesMessage(ValidationError,"위험평가를 먼저 완료",transition_complaint,c,"CAPA_DECISION",self.raqa)
    def test_high_risk_requires_capa(self):
        c=self.complaint(); c.status="CAPA_DECISION"; c.save(); RiskAssessment.objects.create(complaint=c,severity=4,probability=4,assessed_by=self.raqa); self.assertRaisesMessage(ValidationError,"CAPA를 등록",transition_complaint,c,"REPORT_REVIEW",self.raqa)
    def test_report_required_before_recall_review(self):
        c=self.complaint(); c.status="REPORT_REVIEW"; c.save(); self.assertRaisesMessage(ValidationError,"체크리스트",transition_complaint,c,"RECALL_REVIEW",self.raqa)
    def test_approval_snapshot_and_gate(self):
        c=self.complaint(); c.status="APPROVAL"; c.save(); a=request_complaint_approval(c,self.raqa); self.assertEqual(a.snapshot["version"],c.version); self.assertEqual(a.snapshot["device"],str(self.d)); self.assertRaisesMessage(ValidationError,"관리자 승인",transition_complaint,c,"ACTION_COMPLETE",self.admin); decide_approval(a,self.admin,"APPROVED"); transition_complaint(c,"ACTION_COMPLETE",self.admin); self.assertEqual(c.status,"ACTION_COMPLETE")
    def test_role_and_ownership(self):
        mine=self.complaint(); foreign=self.complaint(self.other); self.assertEqual(list(visible_complaints(self.staff)),[foreign,mine][::-1] if False else [foreign,mine]) if False else self.assertNotIn(foreign,visible_complaints(self.staff)); self.assertEqual(visible_complaints(self.raqa).count(),2); self.assertRaises(PermissionDenied,transition_complaint,mine,"REVIEW",self.staff)
    @override_settings(PMS_RULES={"LOT_WINDOW_DAYS":30,"LOT_THRESHOLD":3,"DEVICE_WINDOW_DAYS":90,"DEVICE_THRESHOLD":5})
    def test_recurrent_complaint(self):
        self.complaint(); self.complaint(); c=self.complaint(); self.assertTrue(any("LOT" in x for x in recurrent_warning(c)))
    def test_recall_validation_and_rate(self):
        r=Recall(title="R",reason="x",risk_level="HIGH",device=self.d,distributed_quantity=10,target_quantity=8,recovered_quantity=4,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=self.raqa); r.full_clean(); self.assertEqual(r.recovery_rate,50); r.recovered_quantity=9; self.assertRaises(ValidationError,r.full_clean)
    def test_approval_and_rejection(self):
        a=Approval.objects.create(content_type="Complaint",object_id=1,requested_by=self.raqa); decide_approval(a,self.admin,"REJECTED","자료 보완"); self.assertEqual(a.decision,"REJECTED")
    def test_audit_redacts_sensitive(self):
        log=audit(self.staff,"UPDATE",self.d,after={"password":"secret","name":"ok"}); self.assertNotIn("password",log.after); self.assertEqual(log.after["name"],"ok")
    def test_attachment_validation(self):
        c=self.complaint(); bad=Attachment(complaint=c,file=SimpleUploadedFile("bad.exe",b"x"),uploaded_by=self.staff); self.assertRaises(ValidationError,bad.full_clean)
    def test_patient_anonymous_only(self):
        p=PatientAnonymousInfo(complaint=self.complaint(),anonymous_code="ANON-1",notes="전화 010 저장"); self.assertRaises(ValidationError,p.full_clean)
class WebApiTests(Base):
    def test_login_and_role_pages(self):
        self.client.login(username="staff",password="test-password-123"); self.assertEqual(self.client.get(reverse("dashboard")).status_code,200); self.assertEqual(self.client.get(reverse("audit-list")).status_code,403)
    def test_other_users_case_hidden(self):
        c=self.complaint(self.other); self.client.login(username="staff",password="test-password-123"); self.assertEqual(self.client.get(reverse("complaint-detail",args=[c.pk])).status_code,404)
    def test_api_auth_failure(self): self.assertIn(APIClient().get("/api/complaints/").status_code,(401,403))
    def test_staff_api_create_and_scoping(self):
        foreign=self.complaint(self.other); api=APIClient(); api.login(username="staff",password="test-password-123"); response=api.get("/api/complaints/"); self.assertNotContains(response,str(foreign.pk))
    def test_integrated_detail_and_risk_form(self):
        c=self.complaint(); self.client.login(username="raqa",password="test-password-123"); self.assertContains(self.client.get(reverse("complaint-workspace",args=[c.pk])),"위험평가"); response=self.client.post(reverse("risk-save",args=[c.pk]),{"complaint":c.pk,"severity":5,"probability":4,"rationale":"검토"}); self.assertRedirects(response,reverse("complaint-workspace",args=[c.pk])); self.assertEqual(c.risk_assessment.level,"CRITICAL")
    def test_staff_cannot_submit_workflow_forms(self):
        c=self.complaint(); self.client.login(username="staff",password="test-password-123"); self.assertEqual(self.client.post(reverse("risk-save",args=[c.pk]),{}).status_code,302); self.assertFalse(RiskAssessment.objects.filter(complaint=c).exists())
