from datetime import date, timedelta
from unittest.mock import patch
from django.test import override_settings
from django.urls import reverse
from django.core.exceptions import PermissionDenied, ValidationError
from .tests import Base
from .models import CustomerComplaint, RiskAssessment, SafetySignal, SafetyReview, Notification, CAPA, MedicalDevice, UDI, ProductLot
from .safety import SafetyFilter, analyze_safety, detect, review_signal
from .services import request_complaint_approval, decide_approval, transition_complaint, recurrent_warning


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SafetyTests(Base):
    def params(self, **changes):
        params=dict(start="2026-10-01",end="2026-10-28",interval="week",example="real")
        params.update(changes)
        form=SafetyFilter(self.raqa,params)
        self.assertTrue(form.is_valid(),form.errors)
        return form.cleaned_data

    def case(self,day="2026-10-01",user=None):
        c=self.complaint(user)
        c.reported_on=date.fromisoformat(day);c.save()
        return c

    def test_boundaries_equal_previous_length_and_zero(self):
        for day in ("2026-09-02","2026-09-03","2026-09-30","2026-10-01","2026-10-28","2026-10-29"):
            self.case(day)
        result=analyze_safety(self.raqa,self.params())
        self.assertEqual((result["total"],result["previous_total"]),(2,2))
        self.assertEqual(result["previous_start"],date(2026,9,3))
        self.assertIsNone(result["rate"])
        self.assertEqual(result["groups"][0]["increase"],0)
        CustomerComplaint.objects.filter(reported_on__lt=date(2026,10,1)).delete()
        self.assertIsNone(analyze_safety(self.raqa,self.params())["groups"][0]["increase"])

    @override_settings(SAFETY_RULES=dict(VERSION="test-v1",COUNT=3,MINIMUM=3,LOT_COUNT=3,INCREASE_PERCENT=100))
    def test_thresholds_snapshot_idempotence_history_and_links(self):
        self.case();self.case()
        self.assertEqual(detect(self.raqa,self.params()),[])
        c=self.case()
        first=detect(self.raqa,self.params())[0]
        snapshot=first.snapshot
        self.assertEqual(len(snapshot["evidence"]),3)
        self.assertEqual(detect(self.raqa,self.params())[0].pk,first.pk)
        self.assertEqual(detect(self.raqa,self.params(interval="month"))[0].pk,first.pk)
        self.assertEqual(Notification.objects.filter(dedupe_key__startswith="safety:").count(),1)
        self.case()
        detect(self.raqa,self.params())
        first.refresh_from_db();self.assertEqual(first.snapshot,snapshot)
        review_signal(self.raqa,first.pk,"REVIEW",self.raqa.pk,"초기 검토")
        capa=CAPA.objects.create(complaint=c,title="기존 조치",corrective_action="확인",owner=self.raqa,due_date=date(2026,11,1))
        review_signal(self.raqa,first.pk,"ACTION",self.admin.pk,"기존 조치 연결",capa.pk)
        self.assertEqual(SafetyReview.objects.filter(signal=first).count(),2)
        self.assertEqual(first.history.last().links,{"capa":capa.pk})
        self.assertRaises(PermissionDenied,review_signal,self.staff,first.pk,"CLOSED",self.staff.pk,"우회")
        self.assertRaises(ValidationError,review_signal,self.raqa,first.pk,"ACTION",self.raqa.pk,"누락")

    def test_product_lot_type_filters_and_staff_scope(self):
        self.case();self.case(user=self.other)
        result=analyze_safety(self.staff,self.params(device=self.d.pk,lot=self.lot.pk,complaint_type="TYPE"))
        self.assertEqual(result["total"],1)
        self.assertEqual(analyze_safety(self.raqa,self.params())["total"],2)
        self.assertEqual(analyze_safety(self.staff,self.params(complaint_type="missing"))["total"],0)
        self.assertRaises(PermissionDenied,detect,self.staff,self.params())
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("safety"),dict(start="2026-10-01",end="2026-10-28",interval="month",example="real")),"분모 데이터 없음")

    def test_urgent_and_increase_boundary(self):
        self.case("2026-09-20")
        c=self.case();self.case()
        RiskAssessment.objects.create(complaint=c,severity=5,probability=4,assessed_by=self.raqa)
        with override_settings(SAFETY_RULES=dict(VERSION="test",COUNT=99,MINIMUM=2,LOT_COUNT=99,INCREASE_PERCENT=100)):
            r=analyze_safety(self.raqa,self.params())
            self.assertEqual(r["urgent"],1)
            self.assertIn("이전 동일 길이 기간 대비 증가",r["groups"][0]["reasons"])
        with override_settings(SAFETY_RULES=dict(VERSION="test",COUNT=99,MINIMUM=3,LOT_COUNT=99,INCREASE_PERCENT=100)):
            self.assertNotIn("이전 동일 길이 기간 대비 증가",analyze_safety(self.raqa,self.params())["groups"][0]["reasons"])

    def test_distinct_product_lot_groups_and_constant_query_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.case()
        lot2=ProductLot.objects.create(device=self.d,udi=self.udi,lot_number="L2")
        c=self.case();c.lot=lot2;c.save()
        d2=MedicalDevice.objects.create(manufacturer=self.m,name="Second",model_number="2")
        u2=UDI.objects.create(device=d2,device_identifier="UDI2")
        l3=ProductLot.objects.create(device=d2,udi=u2,lot_number="L3")
        c=self.case();c.device=d2;c.udi=u2;c.lot=l3;c.save()
        with CaptureQueriesContext(connection) as queries:
            result=analyze_safety(self.raqa,self.params())
            list(result["cases"])
        self.assertEqual(len(result["groups"]),3)
        self.assertLessEqual(len(queries),10)
        self.assertEqual(analyze_safety(self.raqa,self.params(device=self.d.pk))["total"],2)
        self.assertEqual(analyze_safety(self.raqa,self.params(lot=lot2.pk))["total"],1)

    def test_no_future_or_invalid_range(self):
        self.assertFalse(SafetyFilter(self.raqa,dict(start="2026-10-28",end="2026-10-01")).is_valid())
        self.assertFalse(SafetyFilter(self.raqa,dict(start="2026-10-01",end="2099-01-01")).is_valid())

    def test_existing_warning_has_scope_and_upper_boundary(self):
        c=self.case()
        self.case(user=self.other);self.case(user=self.other);self.case("2026-10-29")
        self.assertEqual(recurrent_warning(c,user=self.staff),[])

    def test_approval_changes_invalidate_pending_and_approved(self):
        c=self.case();c.status="APPROVAL";c.save()
        a=request_complaint_approval(c,self.raqa)
        c.description="정정";c.save()
        self.assertRaises(ValidationError,decide_approval,a,self.admin,"APPROVED")
        decide_approval(a,self.admin,"REJECTED","변경 후 재검토")
        a=request_complaint_approval(c,self.raqa);decide_approval(a,self.admin,"APPROVED")
        c.description="추가 정정";c.save()
        self.assertRaises(ValidationError,transition_complaint,c,"ACTION_COMPLETE",self.admin)

    def test_signal_http_detail_and_staff_denial(self):
        for _ in range(3): self.case()
        signal=detect(self.raqa,self.params())[0]
        self.client.force_login(self.raqa)
        self.assertContains(self.client.get(reverse("safety-signal",args=[signal.pk])),"탐지 근거")
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("safety-signal",args=[signal.pk])).status_code,404)
