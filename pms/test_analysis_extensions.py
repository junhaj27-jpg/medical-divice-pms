import io
import tempfile
from pathlib import Path
from django.test import override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError, PermissionDenied
from django.core import signing
from .tests import Base
from .models import AdverseEvent, AuditLog, CustomerComplaint, RegulatoryImpact
from .analysis import digest, AnalysisFilter, analyze, save_review
from .analysis_models import AnalysisRecord, AnalysisArtifact
from .internal_cohort import internal_payload, preview_internal, import_internal, confirm_seriousness
from .analysis_archive import generate_analysis_report
from .services import request_complaint_approval, decide_approval, transition_complaint


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class InternalCohortTests(Base):
    def setUp(self):
        super().setUp();self.c=self.complaint()
        self.client.force_login(self.raqa)

    def expected(self): return {str(self.c.pk):digest(internal_payload(self.c))}

    def filters(self):
        from .analysis import default_filters
        f=AnalysisFilter(default_filters());self.assertTrue(f.is_valid());return f.cleaned_data

    def test_unknown_minimal_snapshot_and_idempotence(self):
        AdverseEvent.objects.create(complaint=self.c,event_type='TEST',outcome='TEST',narrative='private narrative',serious=False)
        before=(self.c.version,self.c.description,self.c.due_date)
        rows=preview_internal(self.raqa,[self.c.pk]);self.assertEqual(rows[0]['data']['seriousness'],'UNKNOWN')
        ids=import_internal(self.raqa,self.expected());self.assertEqual(len(ids),1)
        self.assertEqual(import_internal(self.raqa,self.expected()),[])
        r=AnalysisRecord.objects.get(pk=ids[0]);self.assertEqual(r.narrative,'');self.assertNotIn('private narrative',str(r.raw))
        self.c.refresh_from_db();self.assertEqual(before,(self.c.version,self.c.description,self.c.due_date))
        self.assertEqual(r.batch.actor,self.raqa);self.assertIsNotNone(r.batch.created_at)

    def test_correction_keeps_review_and_excludes_previous(self):
        first=import_internal(self.raqa,self.expected())[0]
        f=self.filters();f['minimum']=1
        review=save_review(self.raqa,analyze(f)['signals'][0],'REVIEW',self.raqa,'확인')
        snapshot=review.snapshot.copy()
        self.c.title='corrected';self.c.save()
        second=import_internal(self.raqa,self.expected())[0]
        self.assertEqual(AnalysisRecord.objects.get(pk=second).supersedes_id,first)
        self.assertFalse(AnalysisRecord.objects.get(pk=first).is_current)
        self.assertEqual(analyze(f)['total'],1)
        review.refresh_from_db();self.assertEqual(review.snapshot,snapshot)
        self.assertNotEqual(analyze(f)['signals'][0]['key'],review.key)

    def test_changed_preview_rejected(self):
        expected=self.expected();self.c.description='corrected source';self.c.save()
        self.assertRaises(ValidationError,import_internal,self.raqa,expected)
        self.assertEqual(AnalysisRecord.objects.count(),0)

    def test_sample_separation_and_csv_namespace(self):
        from .test_analysis import AnalysisTests
        helper=AnalysisTests();helper.user=self.raqa
        helper.upload([{'source':'INTERNAL','record_id':f'CMP-{self.c.pk}'}])
        import_internal(self.raqa,self.expected())
        self.assertEqual(AnalysisRecord.objects.count(),2)
        self.c.is_example=True;self.c.save();import_internal(self.raqa,self.expected())
        self.assertEqual(AnalysisRecord.objects.filter(origin='INTERNAL',is_current=True,batch__is_example=False).count(),0)
        self.assertEqual(AnalysisRecord.objects.filter(origin='INTERNAL',is_current=True,batch__is_example=True).count(),1)

    def test_confirmation_and_approval_integrity(self):
        self.c.status='APPROVAL';self.c.save()
        a=request_complaint_approval(self.c,self.raqa)
        confirm_seriousness(self.raqa,self.c.pk,'NON_SERIOUS','기록 확인',self.expected()[str(self.c.pk)])
        self.assertRaises(ValidationError,decide_approval,a,self.admin,'APPROVED')
        a=request_complaint_approval(self.c,self.raqa);decide_approval(a,self.admin,'APPROVED')
        import_internal(self.raqa,self.expected())
        self.assertEqual(AnalysisRecord.objects.get().seriousness,'NON_SERIOUS')
        confirm_seriousness(self.raqa,self.c.pk,'UNKNOWN','추가 확인 필요',self.expected()[str(self.c.pk)])
        self.assertRaises(ValidationError,transition_complaint,self.c,'ACTION_COMPLETE',self.admin)
        logs=AuditLog.objects.filter(action='SERIOUSNESS_CONFIRM')
        self.assertNotIn('기록 확인',str(list(logs.values('after'))))

    def test_staff_denied_and_preview_required(self):
        self.assertRaises(PermissionDenied,preview_internal,self.staff,[self.c.pk])
        for url in ('analysis-internal','analysis'):
            self.client.force_login(self.staff);self.assertEqual(self.client.get(reverse(url)).status_code,403)
        self.assertEqual(self.client.post(reverse('analysis-seriousness',args=[self.c.pk]),{}).status_code,403)
        foreign=self.complaint(self.other)
        self.assertEqual(self.client.get(reverse('complaint-detail',args=[foreign.pk])).status_code,404)
        self.client.force_login(self.raqa)
        self.assertRaises(ValidationError,preview_internal,self.raqa,[999999])
        response=self.client.post(reverse('analysis-internal'),{'case_ids':[self.c.pk]})
        token=response.context['token'];self.assertContains(response,'가져오기 전 미리보기: 1건')
        self.client.post(reverse('analysis-internal'),{'action':'import','token':token})
        self.assertEqual(AnalysisRecord.objects.count(),0)
        self.client.post(reverse('analysis-internal'),{'action':'import','token':token,'confirmed':'yes'})
        self.assertEqual(AnalysisRecord.objects.count(),1)
        self.client.post(reverse('analysis-internal'),{'action':'import','token':token,'confirmed':'yes'})
        self.assertEqual(AnalysisRecord.objects.count(),1)

    def test_confirmation_reason_and_stale(self):
        self.assertRaises(ValidationError,confirm_seriousness,self.raqa,self.c.pk,'NON_SERIOUS','',self.expected()[str(self.c.pk)])
        self.assertRaises(ValidationError,confirm_seriousness,self.raqa,self.c.pk,'NON_SERIOUS','확인','stale')

    def test_pdf_version_private_download_and_frozen_review(self):
        import os
        if not os.environ.get('PDF_KOREAN_FONT'): self.skipTest('PDF_KOREAN_FONT 미설정')
        Path('.test-media').mkdir(exist_ok=True)
        import uuid, shutil
        root=Path('.test-media')/uuid.uuid4().hex;root.mkdir()
        self.addCleanup(shutil.rmtree,root)
        with override_settings(MEDIA_ROOT=root):
            import_internal(self.raqa,self.expected());f=self.filters();f['minimum']=1
            review=save_review(self.raqa,analyze(f)['signals'][0],'REVIEW',self.raqa,'초기 검토')
            first=generate_analysis_report(self.raqa,f);old=Path(first.file.path).read_bytes();snapshot=first.snapshot
            save_review(self.raqa,analyze(f)['signals'][0],'CLOSED',self.raqa,'후속 검토')
            second=generate_analysis_report(self.raqa,f)
            self.assertEqual((first.report_id,first.version,second.version),(second.report_id,1,2))
            self.assertEqual(Path(first.file.path).read_bytes(),old)
            first.refresh_from_db();self.assertEqual(first.snapshot,snapshot)
            self.assertEqual(first.snapshot['reviews'][0]['status'],'REVIEW')
            self.assertEqual(second.snapshot['reviews'][0]['status'],'CLOSED')
            self.assertEqual(len(first.snapshot['scope']),1)
            from pypdf import PdfReader
            self.assertIn('발생률 아님',''.join(p.extract_text() for p in PdfReader(io.BytesIO(old)).pages))
            url=reverse('analysis-artifact',args=[first.pk])
            self.assertEqual(self.client.get(url).status_code,200)
            self.assertTrue(AuditLog.objects.filter(action='ANALYSIS_PDF_DOWNLOAD').exists())
            for user in (self.staff,self.other):
                self.client.force_login(user);self.assertEqual(self.client.get(url).status_code,403)
                self.assertEqual(self.client.post(reverse('analysis-pdf-generate'),f).status_code,403)
            self.client.logout();self.assertEqual(self.client.get(url).status_code,302)
            self.client.force_login(self.raqa)
            Path(first.file.path).write_bytes(b'changed')
            self.assertEqual(self.client.get(url).status_code,400)

    @override_settings(PDF_KOREAN_FONT='')
    def test_missing_font_leaves_analysis_available(self):
        import_internal(self.raqa,self.expected())
        self.assertRaises(ValidationError,generate_analysis_report,self.raqa,self.filters())
        self.assertEqual(AnalysisArtifact.objects.count(),0)
        self.assertEqual(self.client.get(reverse('analysis')).status_code,200)
