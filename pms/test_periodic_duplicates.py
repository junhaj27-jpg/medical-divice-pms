import uuid
from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .tests import Base
from .models import PMSPeriodicReport, DuplicateReview, CustomerComplaint, AnalysisImport, AnalysisRecord
from .periodic import create_periodic, finalize_periodic, excluded_ids
from .duplicates import candidates, review_duplicate


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PeriodicDuplicateTests(Base):
    def setUp(self):
        super().setUp();self.c=self.complaint();self.othercase=self.complaint(self.other)
    def payload(self,**kw): return dict(request_key=str(uuid.uuid4()),**kw)
    def report_data(self):
        today=timezone.localdate()
        return self.payload(device=self.d.pk,start=(today-timedelta(days=29)).isoformat(),end=today.isoformat(),is_example=False)
    def decision(self,user,verdict,**kw):
        latest=self.c.duplicate_reviews.order_by('-pk').first()
        return review_duplicate(user,self.c.pk,self.payload(other=self.othercase.pk,verdict=verdict,reason='근거',expected=latest.pk if latest else 0,**kw))
    def count(self,report,label): return next(r['count'] for r in report.snapshot['metrics'] if r['label']==label)

    def test_visibility_comparison_and_suspicion_never_excludes(self):
        self.assertEqual(candidates(self.staff,self.c),[])
        result=candidates(self.raqa,self.c)
        self.assertEqual(result[0]['id'],self.othercase.pk)
        self.assertEqual(len(result[0]['comparisons']),5)
        self.decision(self.raqa,'POSSIBLE')
        self.assertEqual(excluded_ids(self.raqa,False),set())
        self.assertRaises(PermissionDenied,self.decision,self.raqa,'EXCLUDE',confirm=True)
        self.assertEqual(DuplicateReview.objects.count(),1)

    def test_exclusion_history_permissions_frozen_reports_and_restore(self):
        draft=create_periodic(self.raqa,self.report_data())
        self.assertEqual(self.count(draft,'내부 사건 / 기간 내 발생 불만'),2)
        self.decision(self.admin,'EXCLUDE',confirm=True)
        self.assertEqual(excluded_ids(self.raqa,False),{self.c.pk})
        self.decision(self.raqa,'DEFER')
        self.assertEqual(excluded_ids(self.raqa,False),{self.c.pk})
        newer=create_periodic(self.raqa,self.report_data())
        self.assertEqual(self.count(newer,'내부 사건 / 기간 내 발생 불만'),1)
        draft.refresh_from_db();self.assertEqual(self.count(draft,'내부 사건 / 기간 내 발생 불만'),2)
        self.decision(self.admin,'INCLUDE',confirm=True)
        self.assertEqual(excluded_ids(self.raqa,False),set())
        self.assertEqual(self.c.duplicate_reviews.count(),3)

    def test_duplicate_retry_and_stale_concurrent_decision(self):
        data=self.payload(other=self.othercase.pk,verdict='POSSIBLE',reason='근거',expected=0)
        first=review_duplicate(self.raqa,self.c.pk,data)
        self.assertEqual(review_duplicate(self.raqa,self.c.pk,data).pk,first.pk)
        self.assertRaises(ValidationError,review_duplicate,self.raqa,self.c.pk,dict(data,request_key=str(uuid.uuid4())))
        self.assertRaises(ValidationError,review_duplicate,self.raqa,self.c.pk,dict(data,reason='변경'))

    def test_period_comparison_snapshot_review_versions_and_example_separation(self):
        old=self.complaint();old.occurred_on=timezone.localdate()-timedelta(days=30);old.save()
        sample=self.complaint();sample.is_example=True;sample.save()
        data=self.report_data();draft=create_periodic(self.raqa,data)
        self.assertEqual(create_periodic(self.raqa,data).pk,draft.pk)
        self.assertEqual(self.count(draft,'내부 사건 / 기간 내 발생 불만'),2)
        self.assertEqual(self.count(draft,'내부 사건 / 동일 길이 직전 기간 발생 불만'),1)
        self.assertEqual(self.count(draft,'내부 사건 / 중대성 확인 미상'),2)
        finalize=self.payload(review_note='확인 완료',confirm=True)
        final=finalize_periodic(self.admin,draft.pk,finalize)
        self.assertEqual(final.reviewer,self.admin)
        self.assertEqual(final.snapshot,draft.snapshot)
        self.assertEqual(finalize_periodic(self.admin,draft.pk,finalize).pk,final.pk)
        self.assertRaises(ValidationError,finalize_periodic,self.admin,draft.pk,self.payload(review_note='중복',confirm=True))
        self.assertRaises(ValidationError,final.save)
        self.c.delete()
        final.refresh_from_db();self.assertEqual(self.count(final,'내부 사건 / 기간 내 발생 불만'),2)
        newer=create_periodic(self.raqa,self.report_data());self.assertGreater(newer.version,final.version)

    def test_source_cohorts_not_added_together_and_missing_dates(self):
        batch=AnalysisImport.objects.create(filename='test',original=b'',sha256='a'*64,actor=self.raqa,accepted=2)
        for i,origin,date in [(1,'CSV',timezone.localdate()),(2,'INTERNAL',timezone.localdate()),(3,'CSV',None)]:
            AnalysisRecord.objects.create(batch=batch,row_number=i,raw={},source=origin,record_id=str(i),identity=str(i)*64,
                origin=origin,source_case=self.c if origin=='INTERNAL' else None,source_hash='b'*64 if origin=='INTERNAL' else '',
                device=self.d.name,manufacturer=self.m.name,model=self.d.model_number,occurred_on=date,reported_on=timezone.localdate(),event_type='TYPE',seriousness='UNKNOWN')
        draft=create_periodic(self.raqa,self.report_data())
        self.assertEqual(self.count(draft,'내부 사건 / 기간 내 발생 불만'),2)
        self.assertEqual(self.count(draft,'CSV 별도 코호트 / 기간 내 발생 (내부 사건과 합산하지 않음)'),1)
        self.assertEqual(self.count(draft,'CSV 별도 코호트 / 발생일 누락으로 기간 통계 제외'),1)

    def test_confirmed_exclusion_changes_new_statistics_without_rewriting_signals(self):
        from .safety import analyze_safety,detect
        from .models import RiskAssessment
        RiskAssessment.objects.create(complaint=self.c,severity=5,probability=4,assessed_by=self.raqa)
        today=timezone.localdate()
        filters=dict(start=today-timedelta(days=29),end=today,interval='week',example='real')
        signal=detect(self.raqa,filters)[0];snapshot=signal.snapshot
        self.decision(self.raqa,'POSSIBLE')
        self.assertEqual(analyze_safety(self.raqa,filters)['total'],2)
        self.decision(self.admin,'EXCLUDE',confirm=True)
        self.assertEqual(analyze_safety(self.raqa,filters)['total'],1)
        signal.refresh_from_db();self.assertEqual(signal.snapshot,snapshot)

    def test_internal_active_counts_apply_exclusion_and_archive_preserves_versions(self):
        from .internal_cohort import preview_internal,import_internal
        def take_snapshot():
            rows=preview_internal(self.raqa,[self.c.pk])
            import_internal(self.raqa,{str(r['data']['case_id']):r['hash'] for r in rows})
        active_label='내부 가져오기 코호트 / 기간 내 (원본 사건과 중복 합산하지 않음)'
        archive_label='보존 스냅샷 / 내부 가져오기 전체 버전 수'
        take_snapshot()
        first=create_periodic(self.raqa,self.report_data())
        final=finalize_periodic(self.admin,first.pk,self.payload(review_note='원본 확인',confirm=True))
        original=final.snapshot
        self.c.description='정정한 원본 내용';self.c.save()
        take_snapshot()
        self.decision(self.raqa,'POSSIBLE')
        suspected=create_periodic(self.raqa,self.report_data())
        self.assertEqual(self.count(suspected,active_label),1)
        self.assertEqual(self.count(suspected,archive_label),2)
        self.decision(self.admin,'EXCLUDE',confirm=True)
        excluded=create_periodic(self.raqa,self.report_data())
        self.assertEqual(self.count(excluded,active_label),0)
        self.assertEqual(self.count(excluded,archive_label),2)
        self.assertEqual(AnalysisRecord.objects.filter(source_case=self.c).count(),2)
        final.refresh_from_db();self.assertEqual(final.snapshot,original)
        self.assertEqual(self.count(final,archive_label),1)
        active=next(r for r in excluded.snapshot['metrics'] if r['label']==active_label)
        archive=next(r for r in excluded.snapshot['metrics'] if r['label']==archive_label)
        self.assertEqual(active['evidence'],[])
        self.assertEqual(len(archive['evidence']),2)
        self.assertEqual(archive['count_unit'],'스냅샷')
        self.client.force_login(self.raqa)
        page=self.client.get(reverse('periodic-detail',args=[excluded.pk]))
        self.assertContains(page,'집계 제외 사건과 정정 전 버전도 포함합니다.')
        self.decision(self.admin,'INCLUDE',confirm=True)
        restored=create_periodic(self.raqa,self.report_data())
        self.assertEqual(self.count(restored,active_label),1)
        self.assertEqual(self.count(restored,archive_label),2)

    def test_screen_api_permissions_and_no_foreign_case_leak(self):
        self.client.force_login(self.staff)
        response=self.client.get(reverse('duplicate-review',args=[self.c.pk]))
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,f'비교 사건 #{self.othercase.pk}')
        self.assertEqual(self.client.get(reverse('duplicate-review',args=[self.othercase.pk])).status_code,404)
        api=APIClient();api.force_authenticate(self.staff)
        self.assertEqual(api.get('/api/pms-reviews/').status_code,403)
        self.assertEqual(api.post(f'/api/complaints/{self.c.pk}/duplicates/',{},format='json').status_code,403)
        self.client.force_login(self.raqa)
        self.assertEqual(self.client.get(reverse('periodic-list')).status_code,200)
        draft=create_periodic(self.raqa,self.report_data())
        self.assertContains(self.client.get(reverse('periodic-detail',args=[draft.pk])),'산출 근거 목록')
        api.force_authenticate(self.raqa)
        self.assertEqual(api.get(f'/api/pms-reviews/{draft.pk}/').status_code,200)

    def test_final_pdf_is_preserved_private_and_receipt_metrics_are_separate(self):
        import hashlib, io
        from pypdf import PdfReader
        draft=create_periodic(self.raqa,self.report_data())
        self.assertEqual(self.count(draft,'내부 사건 / 기간 내 접수 불만'),2)
        final=finalize_periodic(self.admin,draft.pk,self.payload(review_note='검토 완료',confirm=True))
        content=bytes(final.pdf_content)
        self.assertEqual(hashlib.sha256(content).hexdigest(),final.pdf_sha256)
        self.assertIn('내부 PMS 정기 검토 보고서',''.join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages))
        self.c.title='후속 변경';self.c.save()
        final.refresh_from_db();self.assertEqual(bytes(final.pdf_content),content)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('periodic-pdf',args=[final.pk])).status_code,403)
        self.client.force_login(self.raqa)
        self.assertEqual(self.client.get(reverse('periodic-pdf',args=[final.pk])).content,content)
        api=APIClient();api.force_authenticate(self.raqa)
        self.assertNotIn('pdf_content',api.get(f'/api/pms-reviews/{final.pk}/').json()[0])
