import uuid
import hashlib
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from .tests import Base
from .models import *
from .signal_tracking import track_signal
from .submissions import prepare_submission, record_submission
from .services import request_complaint_approval, decide_approval, approval_is_current
from .approval_integrity import approval_snapshot
from .safety import review_signal


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TrackingTests(Base):
    def setUp(self):
        super().setUp()
        self.c=self.complaint()
        self.signal=SafetySignal.objects.create(key='test',scope='professional',snapshot={'group':{'device_id':self.d.pk},'evidence':[{'pk':self.c.pk}]},assignee=self.raqa)
        # Match the established scope, rather than invent an authorization bypass.
        from .safety import scope_for
        self.signal.scope=scope_for(self.raqa);self.signal.save()
        media=Path("work/tracking-tests")/uuid.uuid4().hex
        media.mkdir(parents=True)
        self.settings_override=override_settings(MEDIA_ROOT=str(media.resolve()));self.settings_override.enable();self.addCleanup(self.settings_override.disable)

    def payload(self,**kw): return dict(request_key=str(uuid.uuid4()),note='검토 근거',**kw)

    def signal_do(self,kind,**kw): return track_signal(self.raqa,self.signal.pk,self.payload(kind=kind,**kw))

    def approved_report(self):
        report=RegulatoryReport.objects.create(complaint=self.c,document_number='R1',submission_authority='기관',submission_channel='수동 포털',required=True,author=self.raqa)
        self.c.status='APPROVAL';self.c.save()
        decide_approval(request_complaint_approval(self.c,self.raqa),self.admin,'APPROVED')
        content=b'%PDF-1.4 frozen test bytes'
        artifact=ReportArtifact(complaint=self.c,number='R',version=1,snapshot={'approval_content_hash':approval_snapshot(self.c)['hash']},generated_by=self.raqa,sha256=hashlib.sha256(content).hexdigest())
        artifact.file.save('test.pdf',ContentFile(content),save=True)
        data=self.payload(report_kind='INITIAL',artifact=artifact.pk,authority='기관',channel='수동 포털')
        return report,artifact,data

    def test_signal_investigation_no_action_close_reopen_and_roles(self):
        self.assertRaises(PermissionDenied,track_signal,self.staff,self.signal.pk,self.payload(kind='CLOSE'))
        self.assertRaises(ValidationError,review_signal,self.raqa,self.signal.pk,'CLOSED',self.raqa.pk,'우회')
        self.signal_do('INVESTIGATE',basis='확인 근거',due_on='2026-12-01',assignee=self.admin.pk)
        self.signal_do('NO_ACTION')
        self.signal_do('CLOSE')
        self.signal.refresh_from_db();self.assertEqual(self.signal.status,'CLOSED')
        self.signal_do('REOPEN');self.signal.refresh_from_db();self.assertEqual(self.signal.status,'REVIEW')
        self.assertEqual(self.signal.tracking.count(),4)
        self.assertEqual(self.signal.tracking.first().actor,self.raqa)

    def test_signal_explicit_draft_retry_scope_and_incomplete_closure(self):
        data=self.payload(kind='DRAFT_CAPA',complaint=self.c.pk,due_on='2026-12-01',confirm=True)
        self.assertRaises(ValidationError,track_signal,self.raqa,self.signal.pk,dict(data,confirm=False))
        first=track_signal(self.raqa,self.signal.pk,data)
        self.assertEqual(track_signal(self.raqa,self.signal.pk,data).pk,first.pk)
        self.assertEqual(CAPA.objects.count(),1)
        self.assertRaises(ValidationError,track_signal,self.raqa,self.signal.pk,dict(data,note='다른 요청'))
        self.assertRaises(ValidationError,track_signal,self.raqa,self.signal.pk,dict(data,request_key=str(uuid.uuid4())))
        self.assertRaises(ValidationError,review_signal,self.raqa,self.signal.pk,'CLOSED',self.raqa.pk,'종결')
        other=self.complaint(self.other)
        bad=CAPA.objects.create(complaint=other,title='다른 사건',owner=self.raqa,corrective_action='x',due_date=timezone.localdate())
        self.assertRaises(ValidationError,self.signal_do,'LINK',capa=bad.pk)

    def test_reopened_or_deferred_signal_requires_fresh_decision(self):
        self.signal_do('INVESTIGATE',basis='근거',due_on='2026-12-01')
        self.signal_do('NO_ACTION')
        self.signal_do('CLOSE')
        self.signal_do('REOPEN')
        self.assertRaises(ValidationError,self.signal_do,'CLOSE')
        for kind in ('HOLD','ACTION_REQUIRED','INVESTIGATE'):
            self.signal_do('NO_ACTION')
            args={'basis':'추가 근거','due_on':'2026-12-02'} if kind=='INVESTIGATE' else {}
            self.signal_do(kind,**args)
            self.assertRaises(ValidationError,self.signal_do,'CLOSE')
        self.signal_do('NO_ACTION')
        self.signal_do('CLOSE')
        self.assertEqual(self.signal.tracking.filter(kind='NO_ACTION').count(),5)

    def test_investigation_deadline_uses_user_timezone_and_task_history(self):
        task=WorkTask.objects.create(complaint=self.c,assignee=self.raqa,title='조사',due_at=timezone.now())
        self.signal.task=task;self.signal.save(update_fields=['task'])
        with timezone.override('Asia/Seoul'):
            self.signal_do('INVESTIGATE',basis='근거',due_on='2026-12-01')
            task.refresh_from_db()
            self.assertEqual(timezone.localtime(task.due_at).isoformat(),'2026-12-01T23:59:59+09:00')
        from rest_framework.test import APIClient
        api=APIClient();api.force_authenticate(self.raqa)
        data=self.payload(kind='CLOSE')
        self.assertEqual(api.post(f'/api/safety/signals/{self.signal.pk}/tracking/',data,format='json').status_code,400)
        self.client.force_login(self.raqa)
        page=self.client.post(reverse('signal-tracking',args=[self.signal.pk]),data)
        self.assertContains(page,'최신 조사·재검토 이후 조치 불필요 사유 검토가 필요합니다.')

    def test_submission_explicit_state_retry_and_reapproval(self):
        report,artifact,data=self.approved_report()
        v=prepare_submission(self.raqa,report.pk,data)
        self.assertEqual(prepare_submission(self.raqa,report.pk,data).pk,v.pk)
        self.assertRaises(PermissionDenied,prepare_submission,self.staff,report.pk,data)
        self.assertRaises(ValidationError,record_submission,self.raqa,v.pk,self.payload(state='COMPLETED'))
        send=self.payload(state='SUBMITTED',confirm=True,submitted_at=timezone.now().isoformat(),submitter='RA 담당')
        self.assertRaises(ValidationError,record_submission,self.raqa,v.pk,dict(send,confirm=False))
        event=record_submission(self.raqa,v.pk,send)
        self.assertEqual(record_submission(self.raqa,v.pk,send).pk,event.pk)
        self.c.description='승인 후 내용 변경';self.c.save()
        self.assertFalse(approval_is_current(self.c))
        self.assertRaises(ValidationError,prepare_submission,self.raqa,report.pk,dict(data,request_key=str(uuid.uuid4())))
        self.assertEqual(SubmissionVersion.objects.get(pk=v.pk).content_hash,v.content_hash)

    def test_administrative_evidence_does_not_invalidate_approval(self):
        report,artifact,data=self.approved_report();v=prepare_submission(self.raqa,report.pk,data)
        record_submission(self.raqa,v.pk,self.payload(state='SUBMITTED',confirm=True,submitted_at=timezone.now().isoformat(),submitter='RA'))
        content=b'receipt'
        a=Attachment(complaint=self.c,uploaded_by=self.raqa,purpose='ADMIN',scan_status='PASSED',sha256=hashlib.sha256(content).hexdigest(),detected_type='txt')
        a.file.save('receipt.txt',ContentFile(content),save=True)
        self.assertTrue(approval_is_current(self.c))
        record_submission(self.raqa,v.pk,self.payload(state='ACKNOWLEDGED',evidence=[a.pk],receipt_number='A-1'))
        self.assertTrue(approval_is_current(self.c))
        self.assertRaises(ValidationError,record_submission,self.raqa,v.pk,self.payload(state='SUPPLEMENT_REQUESTED',evidence=[a.pk],due_at=timezone.now().isoformat()))

    def test_metadata_correction_preserves_submission_and_state(self):
        report,artifact,data=self.approved_report();v=prepare_submission(self.raqa,report.pk,data)
        original=record_submission(self.raqa,v.pk,self.payload(state='SUBMITTED',confirm=True,submitted_at=timezone.now().isoformat(),submitter='RA'))
        correction=self.payload(state='CORRECT_METADATA',receipt_number='corrected-1',assignee=self.admin.pk)
        fixed=record_submission(self.raqa,v.pk,correction)
        self.assertEqual(fixed.state,'SUBMITTED')
        self.assertEqual(fixed.data['corrects_event'],original.pk)
        self.assertEqual(record_submission(self.raqa,v.pk,correction).pk,fixed.pk)
        original.refresh_from_db();self.assertEqual(original.data['submitter'],'RA')
        self.assertTrue(approval_is_current(self.c))
        self.assertRaises(ValidationError,record_submission,self.raqa,v.pk,dict(correction,request_key=str(uuid.uuid4()),submitter='changed'))
        self.assertRaises(ValidationError,record_submission,self.raqa,v.pk,dict(correction,request_key=str(uuid.uuid4()),assignee=self.staff.pk))

    def test_screen_api_role_and_submission_status_bypass(self):
        report,artifact,data=self.approved_report()
        from rest_framework.test import APIClient
        api=APIClient();api.force_authenticate(self.staff)
        self.assertEqual(api.post(f'/api/reports/{report.pk}/tracking/',data,format='json').status_code,403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('report-tracking',args=[report.pk])).status_code,403)
        self.client.force_login(self.raqa)
        self.assertEqual(self.client.get(reverse('report-tracking',args=[report.pk])).status_code,200)
        api.force_authenticate(self.raqa)
        self.assertEqual(api.patch(f'/api/reports/{report.pk}/',{'status':'SUBMITTED'},format='json').status_code,400)
        self.assertEqual(api.post(f'/api/reports/{report.pk}/tracking/',data,format='json').status_code,200)
        report.status='SUBMITTED'
        self.assertRaises(ValidationError,report.save)

    def test_plan_change_invalidates_approval_and_does_not_rewrite_submission(self):
        from .submissions import save_submission_plan
        report,artifact,data=self.approved_report();v=prepare_submission(self.raqa,report.pk,data)
        save_submission_plan(self.raqa,report.pk,dict(submission_authority='새 기관',submission_channel='수동'))
        self.assertFalse(approval_is_current(self.c))
        v.refresh_from_db();self.assertEqual(v.snapshot['authority'],'기관')

    def receipt(self):
        content=b'receipt'
        a=Attachment(complaint=self.c,uploaded_by=self.raqa,purpose='ADMIN',scan_status='PASSED',sha256=hashlib.sha256(content).hexdigest(),detected_type='txt')
        a.file.save('receipt.txt',ContentFile(content),save=True)
        return a

    def test_supplement_new_version_receipt_preservation_and_deadline(self):
        report,artifact,data=self.approved_report();v=prepare_submission(self.raqa,report.pk,data)
        record_submission(self.raqa,v.pk,self.payload(state='SUBMITTED',confirm=True,submitted_at=timezone.now().isoformat(),submitter='RA'))
        receipt=self.receipt()
        record_submission(self.raqa,v.pk,self.payload(state='SUPPLEMENT_REQUESTED',evidence=[receipt.pk],due_at=(timezone.now()+timedelta(days=10)).isoformat(),due_reason='기관 보완 요청서 기한'))
        request_event=v.events.last()
        update=record_submission(self.raqa,v.pk,self.payload(state='UPDATE_FOLLOWUP',assignee=self.admin.pk,due_at=(timezone.now()+timedelta(days=11)).isoformat(),due_reason='담당자 확인한 수동 기한 정정'))
        self.assertEqual(update.state,'SUPPLEMENT_REQUESTED')
        self.assertEqual(update.data['updates_event'],request_event.pk)
        self.assertEqual(update.data['assignee_id'],self.admin.pk)
        request_event.refresh_from_db();self.assertNotEqual(request_event.data['due_at'],update.data['due_at'])
        from django.db import transaction
        with self.assertRaises(ValidationError), transaction.atomic(): receipt.delete()
        receipt.sha256='x'*64;self.assertRaises(ValidationError,receipt.save)
        v2=prepare_submission(self.raqa,report.pk,dict(data,request_key=str(uuid.uuid4()),report_kind='FOLLOWUP'))
        record_submission(self.raqa,v.pk,self.payload(state='SUPPLEMENT_SUBMITTED',replacement=v2.pk,confirm=True,submitted_at=timezone.now().isoformat(),submitter='RA'))
        self.assertEqual(v2.events.last().state,'SUBMITTED')
        self.assertEqual(v.events.last().state,'SUPPLEMENT_SUBMITTED')
        self.assertEqual(v.snapshot['pdf_sha256'],v2.snapshot['pdf_sha256'])

    def test_existing_capa_evaluation_reused_and_fail_reopens_signal(self):
        from .workflow import evaluate_capa,close_capa
        draft=self.signal_do('DRAFT_CAPA',complaint=self.c.pk,due_on='2026-12-01',confirm=True)
        capa=draft.capa
        args=dict(action_result='완료',criteria='기준',scheduled_on=timezone.localdate(),evaluated_on=timezone.localdate(),verdict='FAIL',rationale='미흡')
        failed=evaluate_capa(capa,self.raqa,args)
        self.signal.refresh_from_db();self.assertEqual(self.signal.status,'REVIEW')
        self.assertEqual(self.signal.tracking.last().evaluation_id,failed.pk)
        failed.followup.status='DONE';failed.followup.save()
        proof=self.receipt_content()
        passed=evaluate_capa(capa,self.raqa,dict(args,verdict='PASS'),evidence=[proof])
        close_capa(capa,self.raqa)
        tracked=self.signal_do('EFFECT',evaluation=passed.pk)
        self.assertEqual(tracked.evaluation_id,passed.pk)
        self.signal_do('CLOSE')
        self.assertEqual(capa.evaluations.count(),2)

    def receipt_content(self):
        content=b'effect proof'
        a=Attachment(complaint=self.c,uploaded_by=self.raqa,purpose='CONTENT',scan_status='PASSED',sha256=hashlib.sha256(content).hexdigest(),detected_type='txt')
        a.file.save('effect.txt',ContentFile(content),save=True)
        return a

    def test_real_pdf_submission_hash_and_private_download(self):
        from pathlib import Path
        from .reporting import generate_report
        font=Path('C:/Windows/Fonts/malgun.ttf')
        if not font.is_file(): self.skipTest('한글 PDF 글꼴 없음')
        report,unused,data=self.approved_report()
        with override_settings(PDF_KOREAN_FONT=str(font)):
            artifact=generate_report(self.c,self.raqa)
        v=prepare_submission(self.raqa,report.pk,dict(data,artifact=artifact.pk))
        self.assertEqual(v.snapshot['pdf_sha256'],artifact.sha256)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('artifact-download',args=[artifact.pk])).status_code,403)
        self.client.force_login(self.raqa)
        response=self.client.get(reverse('artifact-download',args=[artifact.pk]))
        self.assertEqual(response.status_code,200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))

    def test_preserved_records_reject_orm_bulk_overwrite_and_delete(self):
        from copy import copy
        from .periodic import create_periodic
        from .duplicates import review_duplicate
        report,artifact,data=self.approved_report()
        version=prepare_submission(self.raqa,report.pk,data)
        event=record_submission(self.raqa,version.pk,self.payload(state='SUBMITTED',confirm=True,submitted_at=timezone.now().isoformat(),submitter='RA'))
        tracking=self.signal_do('INVESTIGATE',basis='조사 근거',due_on='2026-12-01')
        periodic=create_periodic(self.raqa,self.payload(device=self.d.pk,start=str(timezone.localdate()),end=str(timezone.localdate()),is_example=False))
        other=self.complaint(self.other)
        duplicate=review_duplicate(self.raqa,self.c.pk,self.payload(other=other.pk,verdict='POSSIBLE',reason='검토',expected=0))
        for obj in (version,event,tracking,periodic,duplicate):
            with self.subTest(model=type(obj).__name__):
                model=type(obj);original=obj.request_hash
                self.assertRaises(ValidationError,model.objects.filter(pk=obj.pk).update,request_hash='x'*64)
                self.assertRaises(ValidationError,model.objects.bulk_update,[obj],['request_hash'])
                self.assertRaises(ValidationError,model.objects.filter(pk=obj.pk).delete)
                clone=copy(obj);clone.pk=None;clone.request_hash='x'*64
                self.assertRaises(ValidationError,model.objects.bulk_create,[clone],update_conflicts=True,update_fields=['request_hash'],unique_fields=['request_key'])
                obj.refresh_from_db();self.assertEqual(obj.request_hash,original)
