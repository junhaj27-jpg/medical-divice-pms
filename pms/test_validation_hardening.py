"""Regressions for independently reproduced approval and API defects."""
from django.test import override_settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from .tests import Base
from .models import AdverseEvent, Recall, PatientAnonymousInfo, CAPA, RegulatoryReport
from .services import request_complaint_approval, decide_approval, transition_complaint, latest_complaint_approval


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class IndependentFindingRegressions(Base):
    def approved(self):
        c=self.complaint();c.status="APPROVAL";c.save()
        a=request_complaint_approval(c,self.raqa)
        decide_approval(a,self.admin,"APPROVED")
        return c

    def test_closure_unchanged_and_changed_requires_reapproval(self):
        c=self.approved()
        transition_complaint(c,"ACTION_COMPLETE",self.admin)
        c.description="changed after action completion";c.save()
        self.assertRaises(ValidationError,transition_complaint,c,"CLOSED",self.admin)
        c.refresh_from_db();self.assertEqual(c.status,"ACTION_COMPLETE")
        self.assertRaises(ValidationError,request_complaint_approval,c,self.raqa)
        a=request_complaint_approval(c,self.raqa,reason="changed evidence reviewed")
        c.refresh_from_db();self.assertEqual(c.status,"APPROVAL")
        self.assertRaises(ValidationError,transition_complaint,c,"ACTION_COMPLETE",self.admin)
        decide_approval(a,self.admin,"APPROVED")
        transition_complaint(c,"ACTION_COMPLETE",self.admin)
        transition_complaint(c,"CLOSED",self.admin)
        c.refresh_from_db();self.assertEqual(c.status,"CLOSED")

    def test_invalid_approval_api_returns_400_and_is_immutable(self):
        c=self.approved();transition_complaint(c,"ACTION_COMPLETE",self.admin)
        c.description="changed";c.save()
        self.client.force_login(self.admin)
        response=self.client.post(f"/api/complaints/{c.pk}/transition/",{"status":"CLOSED"},content_type="application/json")
        self.assertEqual(response.status_code,400)
        c.refresh_from_db();self.assertEqual(c.status,"ACTION_COMPLETE")

    def test_reapproval_button_for_stale_approved_case(self):
        c=self.approved();c.description="changed";c.save()
        self.client.force_login(self.raqa)
        response=self.client.get(reverse("complaint-workspace",args=[c.pk]))
        self.assertContains(response,reverse("approval-request",args=[c.pk]))
        response=self.client.post(reverse("approval-request",args=[c.pk]),{"reason":"자료 정정 후 재검토"})
        self.assertEqual(response.status_code,302)
        self.assertEqual(latest_complaint_approval(c).decision,"PENDING")
        self.assertEqual(c.status,"APPROVAL")

    def test_staff_cannot_reparent_event_or_use_foreign_patient(self):
        mine=self.complaint();foreign=self.complaint(self.other)
        event=AdverseEvent.objects.create(complaint=mine,event_type="test",outcome="test",narrative="synthetic")
        patient=PatientAnonymousInfo.objects.create(complaint=foreign,anonymous_code="synthetic-foreign")
        self.client.force_login(self.staff)
        for data in ({"complaint":foreign.pk,"serious":True},{"patient":patient.pk}):
            response=self.client.patch(f"/api/adverse-events/{event.pk}/",data,content_type="application/json")
            self.assertIn(response.status_code,(400,403))
        event.refresh_from_db();self.assertEqual(event.complaint_id,mine.pk);self.assertFalse(event.serious);self.assertIsNone(event.patient_id)

    def test_recall_management_states_cannot_be_set_by_general_api(self):
        c=self.complaint()
        r=Recall.objects.create(complaint=c,title="synthetic",reason="test",risk_level="HIGH",device=self.d,distributed_quantity=10,target_quantity=10,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=self.raqa)
        for user in (self.raqa,self.admin):
            self.client.force_login(user)
            response=self.client.patch(f"/api/recalls/{r.pk}/",{"approval_status":"APPROVED","progress_status":"CLOSED"},content_type="application/json")
            self.assertEqual(response.status_code,400)
        r.refresh_from_db();self.assertEqual(r.approval_status,"DRAFT");self.assertEqual(r.progress_status,"PLANNED")

    def test_question_validation_is_safe_form_error(self):
        self.client.force_login(self.raqa)
        response=self.client.post(reverse("ra-evidence"),{"question":"synthetic 010-1234-5678","as_of":"2026-10-28"})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"직접 식별정보")

    def test_staff_dashboard_scope_and_safe_chart_encoding(self):
        mine=self.complaint();foreign=self.complaint(self.other)
        Recall.objects.create(complaint=foreign,title="FOREIGN-RECALL-SECRET",reason="test",risk_level="HIGH",device=self.d,distributed_quantity=10,target_quantity=10,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=self.raqa)
        CAPA.objects.create(complaint=foreign,title="foreign",corrective_action="test",owner=self.raqa,due_date=timezone.localdate())
        RegulatoryReport.objects.create(complaint=foreign,document_number="foreign-report",author=self.raqa)
        self.d.name="</script><script>window.__VALIDATION_XSS__=true</script>";self.d.save()
        self.client.force_login(self.staff)
        response=self.client.get(reverse("dashboard"))
        self.assertNotContains(response,"FOREIGN-RECALL-SECRET")
        self.assertEqual(response.context["capas"],0)
        self.assertEqual(response.context["reports"],0)
        self.assertNotIn(b"</script><script>window.__VALIDATION_XSS__=true</script>",response.content)
        self.assertContains(response,"dashboard-products-data")

    def test_device_and_lot_counts_follow_staff_case_scope(self):
        self.complaint();self.complaint(self.other)
        self.client.force_login(self.staff)
        for name,pk in (("device-detail",self.d.pk),("lot-detail",self.lot.pk)):
            response=self.client.get(reverse(name,args=[pk]))
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.context["complaint_count"],1)
        self.client.force_login(self.raqa)
        self.assertEqual(self.client.get(reverse("device-detail",args=[self.d.pk])).context["complaint_count"],2)
