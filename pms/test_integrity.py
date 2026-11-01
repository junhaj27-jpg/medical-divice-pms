from django.test import override_settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse
from rest_framework.test import APIClient
from .tests import Base
from .models import Approval, RiskAssessment, RegulatoryReport, Attachment, AuditLog
from .services import request_complaint_approval, decide_approval, transition_complaint
from .approval_integrity import approval_invalid_reason


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ApprovalIntegrityTests(Base):
    def setUp(self):
        super().setUp()
        self.c=self.complaint();self.c.status='APPROVAL';self.c.save()
        self.risk=RiskAssessment.objects.create(complaint=self.c,severity=2,probability=2,assessed_by=self.raqa)
    def request(self,reason=''): return request_complaint_approval(self.c,self.raqa,reason=reason)
    def change_risk(self):
        self.risk.rationale='changed approval content';self.risk.save()
    def test_changed_content_blocks_pending_and_audits(self):
        a=self.request();self.change_risk()
        self.assertRaisesMessage(ValidationError,'자료 변경',decide_approval,a,self.admin,'APPROVED')
        a.refresh_from_db();self.assertEqual(a.decision,'PENDING')
        self.assertTrue(AuditLog.objects.filter(action='APPROVAL_BLOCKED').exists())
    def test_changed_approved_content_requires_reapproval(self):
        old=self.request();decide_approval(old,self.admin,'APPROVED');self.change_risk()
        self.assertRaises(ValidationError,transition_complaint,self.c,'ACTION_COMPLETE',self.admin)
        new=self.request('위험평가 변경 검토');decide_approval(new,self.admin,'APPROVED')
        transition_complaint(self.c,'ACTION_COMPLETE',self.admin);transition_complaint(self.c,'CLOSED',self.admin)
        old.refresh_from_db();self.assertEqual(old.decision,'APPROVED');self.assertEqual(Approval.objects.count(),2)
    def test_reapproval_after_action_complete(self):
        a=self.request();decide_approval(a,self.admin,'APPROVED');transition_complaint(self.c,'ACTION_COMPLETE',self.admin)
        self.change_risk();self.assertRaises(ValidationError,transition_complaint,self.c,'CLOSED',self.admin)
        a=self.request('조치 완료 후 위험평가 변경 재검토')
        self.c.refresh_from_db();self.assertEqual(self.c.status,'APPROVAL')
        decide_approval(a,self.admin,'APPROVED')
        self.assertRaises(ValidationError,transition_complaint,self.c,'CLOSED',self.admin)
        transition_complaint(self.c,'ACTION_COMPLETE',self.admin)
        transition_complaint(self.c,'CLOSED',self.admin)
    def test_stale_pending_preserved_and_superseded(self):
        a=self.request();before=a.snapshot.copy();self.change_risk();new=self.request('대기 중 위험평가 변경 재검토')
        a.refresh_from_db();self.assertTrue(a.superseded);self.assertEqual(a.snapshot,before);self.assertEqual(a.decision,'PENDING')
        self.assertRaises(ValidationError,decide_approval,a,self.admin,'APPROVED')
        self.assertNotEqual(a.pk,new.pk)
    def test_duplicate_and_invalid_decision_blocked(self):
        a=self.request();self.assertRaises(ValidationError,self.request)
        self.assertRaises(ValidationError,decide_approval,a,self.admin,'PENDING')
        decide_approval(a,self.admin,'REJECTED','needs review')
        self.assertRaises(ValidationError,decide_approval,a,self.admin,'APPROVED')
    def test_legacy_approval_not_valid(self):
        a=Approval.objects.create(content_type='CustomerComplaint',object_id=self.c.pk,requested_by=self.raqa,decision='APPROVED',snapshot={'version':1})
        self.assertRaises(ValidationError,transition_complaint,self.c,'ACTION_COMPLETE',self.admin)
        self.assertTrue(approval_invalid_reason(a,self.c))
    def test_reads_do_not_change_validity(self):
        a=self.request();self.c.refresh_from_db();self.risk.refresh_from_db()
        self.assertEqual(approval_invalid_reason(a,self.c),'')
        decide_approval(a,self.admin,'APPROVED');transition_complaint(self.c,'ACTION_COMPLETE',self.admin)
        self.c.refresh_from_db();self.assertEqual(approval_invalid_reason(a,self.c),'')
    def test_report_and_evidence_changes_detected(self):
        report=RegulatoryReport.objects.create(complaint=self.c,document_number='TEST-INTEGRITY',author=self.raqa,checklist={'reviewed':True})
        a=self.request();report.checklist={'reviewed':False};report.save()
        self.assertTrue(approval_invalid_reason(a,self.c))
        a=self.request('보고 체크리스트 변경 재검토');Attachment.objects.create(complaint=self.c,file='attachments/existing-relative.txt',sha256='a'*64,scan_status='PASSED',uploaded_by=self.staff)
        self.assertTrue(approval_invalid_reason(a,self.c))
        self.assertNotIn('safe',str(a.snapshot));self.assertNotIn('checklist',str(a.snapshot))
    def test_ui_and_api_block_stale_approval(self):
        a=self.request();self.change_risk();self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('complaint-workspace',args=[self.c.pk])),'재승인')
        api=APIClient();api.force_authenticate(self.admin)
        self.assertEqual(api.post(f'/api/approvals/{a.pk}/decide/',{'decision':'APPROVED'}).status_code,400)
        api.force_authenticate(self.staff)
        self.assertEqual(api.post(f'/api/complaints/{self.c.pk}/request_approval/').status_code,403)
    def test_service_permissions(self):
        self.assertRaises(PermissionDenied,request_complaint_approval,self.c,self.staff)
        self.assertRaises(PermissionDenied,decide_approval,self.request(),self.raqa,'APPROVED')
    def test_capa_and_recall_content_detected_without_id_changes(self):
        from .models import CAPA, Recall
        from django.utils import timezone
        capa=CAPA.objects.create(complaint=self.c,title='TEST CAPA',corrective_action='before',owner=self.raqa,due_date=timezone.localdate())
        recall=Recall.objects.create(complaint=self.c,title='TEST recall',reason='TEST',risk_level='LOW',device=self.d,distributed_quantity=10,target_quantity=5,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=self.raqa)
        a=self.request();capa.corrective_action='after';capa.save()
        self.assertTrue(approval_invalid_reason(a,self.c))
        a=self.request('CAPA 시정조치 변경 재검토');recall.closure_report='changed';recall.save()
        self.assertTrue(approval_invalid_reason(a,self.c))
    def test_api_final_transition_uses_current_approval(self):
        a=self.request();decide_approval(a,self.admin,'APPROVED');self.change_risk()
        api=APIClient();api.force_authenticate(self.admin)
        self.assertEqual(api.post(f'/api/complaints/{self.c.pk}/transition/',{'status':'ACTION_COMPLETE'}).status_code,400)

    def test_reapproval_request_reason_survives_decision(self):
        old=self.request();decide_approval(old,self.admin,'APPROVED','최초 검토 완료')
        transition_complaint(self.c,'ACTION_COMPLETE',self.admin)
        self.change_risk();reason='조치 완료 후 위험평가 근거 정정'
        new=self.request(reason)
        self.assertEqual(new.snapshot['request_reason'],reason)
        log=AuditLog.objects.get(action='REAPPROVAL_REQUEST',object_id=str(new.pk))
        self.assertEqual(log.after['reason'],reason)
        decide_approval(new,self.admin,'APPROVED','정정 근거 확인')
        new.refresh_from_db();old.refresh_from_db()
        self.assertEqual(new.snapshot['request_reason'],reason)
        self.assertEqual(new.reason,'정정 근거 확인')
        self.assertEqual(old.reason,'최초 검토 완료')

    def test_unchanged_approval_cannot_be_requested_again_with_reason(self):
        approval=self.request();before=approval.snapshot.copy()
        self.assertRaises(ValidationError,self.request,'중복 요청 사유')
        decide_approval(approval,self.admin,'APPROVED')
        transition_complaint(self.c,'ACTION_COMPLETE',self.admin)
        self.assertRaises(ValidationError,self.request,'변경 없는 재요청')
        approval.refresh_from_db();self.c.refresh_from_db()
        self.assertEqual(self.c.status,'ACTION_COMPLETE')
        self.assertEqual(Approval.objects.count(),1)
        self.assertEqual(approval.snapshot,before)
        self.assertFalse(approval.superseded)

    def test_stale_approved_request_requires_nonblank_reason(self):
        approval=self.request();decide_approval(approval,self.admin,'APPROVED')
        transition_complaint(self.c,'ACTION_COMPLETE',self.admin);self.change_risk()
        for reason in ('','   '):
            self.assertRaises(ValidationError,self.request,reason)
        self.c.refresh_from_db();approval.refresh_from_db()
        self.assertEqual(self.c.status,'ACTION_COMPLETE')
        self.assertEqual(approval.decision,'APPROVED')
        self.assertEqual(Approval.objects.count(),1)
