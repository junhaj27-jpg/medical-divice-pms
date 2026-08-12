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
from .assistant_service import answer_question, validate_question
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
    def test_lot_udi_must_match_device(self):
        other=MedicalDevice.objects.create(manufacturer=self.m,name="Other",model_number="2"); lot=ProductLot(device=other,udi=self.udi,lot_number="BAD"); self.assertRaises(ValidationError,lot.full_clean)
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
    def test_staff_adverse_events_are_scoped(self):
        mine=self.complaint(); foreign=self.complaint(self.other); AdverseEvent.objects.create(complaint=mine,event_type="MINE",outcome="ok",narrative="x"); AdverseEvent.objects.create(complaint=foreign,event_type="FOREIGN",outcome="ok",narrative="x"); self.client.login(username="staff",password="test-password-123"); response=self.client.get(reverse("adverse-list")); self.assertContains(response,"MINE"); self.assertNotContains(response,"FOREIGN")
    def test_recall_reject_reason_and_close_report(self):
        recall=Recall.objects.create(title="R",reason="x",risk_level="HIGH",device=self.d,distributed_quantity=10,target_quantity=8,recovered_quantity=4,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=self.raqa); self.client.login(username="admin",password="test-password-123"); self.client.post(reverse("recall-admin-action",args=[recall.pk]),{"action":"reject"}); recall.refresh_from_db(); self.assertEqual(recall.approval_status,"DRAFT"); self.client.post(reverse("recall-admin-action",args=[recall.pk]),{"action":"approve"}); self.client.post(reverse("recall-admin-action",args=[recall.pk]),{"action":"close","closure_report":"회수 종료 확인"}); recall.refresh_from_db(); self.assertEqual(recall.progress_status,"CLOSED")
    def test_admin_cannot_demote_self(self):
        self.client.login(username="admin",password="test-password-123"); self.client.post(reverse("user-update",args=[self.admin.profile.pk]),{"role":"STAFF","is_active":"on"}); self.admin.profile.refresh_from_db(); self.assertEqual(self.admin.profile.role,"ADMIN")
    def test_assistant_respects_staff_case_scope(self):
        mine=self.complaint(); foreign=self.complaint(self.other); RiskAssessment.objects.create(complaint=mine,severity=5,probability=4,assessed_by=self.raqa); RiskAssessment.objects.create(complaint=foreign,severity=5,probability=4,assessed_by=self.raqa); intent,response=answer_question(self.staff,"고위험 사건 보여줘"); self.assertEqual(intent,"HIGH_RISK"); self.assertIn(f"CMP-{mine.pk:05d}",response); self.assertNotIn(f"CMP-{foreign.pk:05d}",response)
    def test_assistant_rejects_direct_identifiers(self):
        self.assertRaises(ValueError,validate_question,"환자 전화번호 010-1234-5678 확인해줘"); self.assertRaises(ValueError,validate_question,"주민번호 900101-1234567")
    def test_assistant_chat_persists_without_prompt_audit(self):
        self.client.login(username="staff",password="test-password-123"); response=self.client.post(reverse("assistant-chat"),{"message":"업무 흐름 알려줘"}); self.assertRedirects(response,reverse("assistant-chat")); conversation=AssistantConversation.objects.get(user=self.staff); self.assertEqual(conversation.messages.count(),2); log=AuditLog.objects.get(action="ASSISTANT_QUERY"); self.assertEqual(log.after["intent"],"WORKFLOW"); self.assertNotIn("업무 흐름",str(log.after))
    def test_assistant_conversations_are_user_isolated(self):
        mine=AssistantConversation.objects.create(user=self.staff); AssistantMessage.objects.create(conversation=mine,role="USER",content="내 질문"); other=AssistantConversation.objects.create(user=self.other); AssistantMessage.objects.create(conversation=other,role="USER",content="타인 비밀 질문"); self.client.login(username="staff",password="test-password-123"); response=self.client.get(reverse("assistant-chat")); self.assertContains(response,"내 질문"); self.assertNotContains(response,"타인 비밀 질문")
