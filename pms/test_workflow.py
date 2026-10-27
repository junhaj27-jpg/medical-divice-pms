import hashlib
import io
import os
import tempfile
import uuid
import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection, IntegrityError, transaction
from django.test import override_settings, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from .tests import Base
from .models import *
from .workflow import *
from .file_security import scan_attachment, safe_attachment_bytes, validate_upload
from .reporting import generate_report
from .backup import backup, restore_verify


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkflowTests(Base):
    def setUp(self):
        super().setUp(); self.c=self.complaint(); self.tmp=type("TestDirectory",(),{"name":str(Path(settings.BASE_DIR)/".test-media"/uuid.uuid4().hex)})(); Path(self.tmp.name).mkdir(parents=True); self.addCleanup(shutil.rmtree,self.tmp.name)
        self.media=override_settings(MEDIA_ROOT=Path(self.tmp.name)/'media'); self.media.enable(); self.addCleanup(self.media.disable)
    def task(self,**kwargs):
        data=dict(complaint=self.c,assignee=self.staff,title='업무',due_at=timezone.now()+timedelta(days=1)); data.update(kwargs)
        return save_task(WorkTask(**data),self.raqa)
    def capa(self): return CAPA.objects.create(complaint=self.c,title='CAPA',corrective_action='조치',owner=self.raqa,due_date=timezone.localdate())
    def recall(self): return Recall.objects.create(complaint=self.c,title='리콜',reason='사유',device=self.d,risk_level='HIGH',distributed_quantity=100,target_quantity=100,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=self.raqa)
    def recipient(self,unit='개'):
        partner,_=BusinessPartner.objects.get_or_create(name='거래처')
        return save_recipient(RecallRecipient(recall=self.recall(),lot=self.lot,partner=partner,unit=unit,target_quantity=10),self.raqa)
    def attachment(self,name='증빙.txt',data=b'safe'):
        return Attachment.objects.create(complaint=self.c,file=SimpleUploadedFile(name,data),original_name=name,uploaded_by=self.staff)
    def evaluation(self,verdict='PASS'):
        return dict(action_result='조치 완료',criteria='반복 없음',scheduled_on=timezone.localdate(),evaluated_on=timezone.localdate(),verdict=verdict,rationale='점검 결과')
    def rule(self,**kwargs):
        data=dict(name='내부 예시',conditions={},basis='REPORTED',days=3,effective_on=timezone.localdate(),change_reason='예시·운영 적용 전 검토 필요');data.update(kwargs)
        return create_rule(ReportingRule(**data),self.admin)
    def test_task_scope_and_history(self):
        task=self.task(); self.assertIn(task,tasks_for(self.staff)); self.assertNotIn(task,tasks_for(self.other))
        task.due_at+=timedelta(hours=1); task.status='REVIEW'; save_task(task,self.raqa)
        self.assertEqual(task.history.count(),2); self.assertIn('due_at',task.history.last().after)
        self.client.force_login(self.other); self.assertEqual(self.client.get(reverse('task-detail',args=[task.pk])).status_code,404)
    def test_staff_cannot_reassign_or_edit_foreign_case(self):
        task=self.task(); task.assignee=self.other
        self.assertRaises(PermissionDenied,save_task,task,self.staff)
        self.assertRaises(ValidationError,self.task,assignee=self.other)
    @override_settings(TASK_DUE_SOON_DAYS=3)
    def test_deadline_boundaries_and_dedupe(self):
        now=timezone.now(); exact=self.task(due_at=now); overdue=self.task(due_at=now-timedelta(microseconds=1)); boundary=self.task(due_at=now+timedelta(days=3)); outside=self.task(due_at=now+timedelta(days=3,microseconds=1)); self.task(due_at=now-timedelta(days=1),status='DONE')
        self.assertEqual(notify_tasks(now),3); self.assertEqual(notify_tasks(now),0)
        self.assertEqual(Notification.objects.filter(dedupe_key__endswith='OVERDUE').count(),1)
        exact.status='DONE'; save_task(exact,self.raqa); self.assertEqual(notify_tasks(now),0)
    def test_deadline_views(self):
        self.task(due_at=timezone.now()-timedelta(seconds=1)); self.client.force_login(self.staff)
        response=self.client.get(reverse('task-list')+'?filter=overdue'); self.assertContains(response,'업무')
    def test_capa_close_requires_pass_and_information(self):
        capa=self.capa(); self.assertRaises(ValidationError,close_capa,capa,self.raqa)
        evaluate_capa(capa,self.raqa,self.evaluation()); close_capa(capa,self.raqa); capa.refresh_from_db(); self.assertEqual(capa.status,'CLOSED')
    def test_capa_fail_followup_and_reevaluation_history(self):
        capa=self.capa(); ev=evaluate_capa(capa,self.raqa,self.evaluation('FAIL')); self.assertEqual(ev.followup.capa,capa)
        self.assertRaises(ValidationError,close_capa,capa,self.raqa)
        ev2=evaluate_capa(capa,self.raqa,self.evaluation()); self.assertEqual(capa.evaluations.count(),2)
        self.assertRaises(ValidationError,close_capa,capa,self.raqa)
        task=ev.followup;task.status='DONE';save_task(task,self.raqa);close_capa(capa,self.raqa)
        self.assertEqual(CAPAEvaluation.objects.get(pk=ev.pk).verdict,'FAIL')
    def test_capa_evidence_same_case_and_passed(self):
        capa=self.capa(); attachment=self.attachment(); self.assertRaises(ValidationError,evaluate_capa,capa,self.raqa,self.evaluation(),[attachment])
        attachment.scan_status='PASSED';attachment.complaint=self.complaint(self.other);attachment.save()
        self.assertRaises(ValidationError,evaluate_capa,capa,self.raqa,self.evaluation(),[attachment])
    def test_partial_cumulative_and_over_recovery(self):
        row=self.recipient(); record_recovery(row,self.raqa,3,timezone.localdate()); record_recovery(row,self.raqa,4,timezone.localdate())
        self.assertEqual((row.recovered_quantity,row.remaining_quantity),(7,3))
        self.assertRaises(ValidationError,record_recovery,row,self.raqa,4,timezone.localdate()); self.assertRaises(ValidationError,record_recovery,row,self.raqa,-1,timezone.localdate())
        row.refresh_from_db();self.assertEqual(row.recovered_total,7)
    def test_stale_recipient_does_not_bypass_limit(self):
        a=self.recipient(); b=RecallRecipient.objects.get(pk=a.pk);record_recovery(a,self.raqa,8,timezone.localdate());self.assertRaises(ValidationError,record_recovery,b,self.raqa,3,timezone.localdate())
        self.assertEqual(a.recoveries.count(),1)
    def test_units_separate_and_contacts(self):
        a=self.recipient('개'); b=save_recipient(RecallRecipient(recall=a.recall,lot=self.lot,partner=a.partner,unit='상자',target_quantity=2),self.raqa)
        totals=recall_totals(a.recall);self.assertEqual(set(totals),{'개','상자'}); self.assertEqual(totals['개']['target'],10)
        record_contact(RecallContact(recipient=a,contacted_at=timezone.now(),method='전화',note='회수 확인'),self.raqa);self.assertEqual(a.contacts.count(),1)
    def test_rule_effective_version_and_preserved_deadline(self):
        from .regulatory import revise_rule,save_draft
        first=self.rule()
        # A pre-upgrade applied version is retained, never silently re-approved.
        ReportingRule.objects.filter(pk=first.pk).update(state='LEGACY');first.refresh_from_db()
        due=timezone.now()+timedelta(days=3)
        app=RuleApplication.objects.create(complaint=self.c,rule=first,snapshot={'version':1,'days':3},due_at=due,actor=self.admin,reason='기존 적용 이력 fixture')
        self.c.due_date=timezone.localdate()+timedelta(days=3);self.c.save()
        second=revise_rule(first,self.admin,'기존 규칙 근거 재검토');second.days=7;second=save_draft(second,self.admin,'새 초안',second.revision)
        self.c.refresh_from_db();self.assertEqual(self.c.due_date,timezone.localdate()+timedelta(days=3))
        self.assertRaises(ValidationError,apply_rule,self.c,self.raqa,second.name,'승인 없는 우회')
        app.refresh_from_db();self.assertEqual(app.due_at,due);self.assertEqual(app.snapshot,{'version':1,'days':3})
        first.days=100;self.assertRaises(ValidationError,first.save)
    def test_structured_rule_rejects_code(self):
        self.assertRaises(ValidationError,self.rule,conditions={'eval':'anything'})
        self.assertRaises(ValidationError,self.rule,conditions={'serious':'true'})
        self.assertRaises(PermissionDenied,create_rule,ReportingRule(),self.staff)
    def test_business_calendar_and_rule_no_obsolete_fallback(self):
        from .regulatory import calculate_deadline
        from datetime import date,time
        self.c.reported_on=date(2026,10,23);self.c.save()
        rule=self.rule(days=1,effective_on=date(2026,10,1),day_type='BUSINESS',holidays=['2026-10-26'],deadline_unit='DAYS',include_start=False,deadline_time=time(18),timezone_name='Asia/Seoul',holiday_verified_from=date(2026,10,1),holiday_verified_until=date(2026,10,31),holiday_checked_on=timezone.localdate())
        result=calculate_deadline(rule,'2026-10-23T10:00:00+09:00')
        self.assertEqual(result['due_at'],'2026-10-27T18:00:00+09:00')
        self.assertRaises(ValidationError,apply_rule,self.c,self.raqa,rule.name,'미승인 구버전 우회')
    def test_unscanned_download_blocked(self):
        obj=self.attachment(); self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('attachment-download',args=[obj.pk])).status_code,403)
        for status in ('FAILED','QUARANTINED'):
            obj.scan_status=status;obj.save();self.assertRaises(PermissionDenied,safe_attachment_bytes,obj)
        self.assertEqual(self.client.get('/media/'+obj.file.name).status_code,404)
    @override_settings(ANTIVIRUS_COMMAND=[])
    def test_missing_scanner_fails_closed(self):
        obj=self.attachment();scan_attachment(obj,self.staff);self.assertEqual(obj.scan_status,'FAILED')
    @override_settings(ANTIVIRUS_COMMAND=['scanner'])
    def test_scan_results_and_tamper(self):
        obj=self.attachment()
        with patch('pms.file_security.subprocess.run') as run:
            run.return_value.returncode=0;scan_attachment(obj,self.staff);self.assertEqual(safe_attachment_bytes(obj),b'safe')
            run.return_value.returncode=1;scan_attachment(obj,self.staff);self.assertEqual(obj.scan_status,'QUARANTINED')
            run.side_effect=TimeoutError();scan_attachment(obj,self.staff);self.assertEqual(obj.scan_status,'FAILED')
        obj.scan_status='PASSED';obj.save();Path(obj.file.path).write_bytes(b'changed');self.assertRaises(PermissionDenied,safe_attachment_bytes,obj)
    def test_extension_content_size_and_filename(self):
        self.assertRaises(ValidationError,validate_upload,SimpleUploadedFile('x.png',b'not png'))
        self.assertRaises(ValidationError,validate_upload,SimpleUploadedFile('x.txt',b'<script>alert(1)</script>'))
        from .file_security import normalized_name
        self.assertEqual(normalized_name('../../bad.txt'),'bad.txt')
        self.assertEqual(normalized_name('C:\\tmp\\bad.txt'),'bad.txt')
    @override_settings(LOGIN_ATTEMPT_LIMIT=2,LOGIN_WINDOW_SECONDS=900)
    def test_login_account_ip_limit(self):
        url=reverse('login');self.assertEqual(self.client.post(url,{'username':'none','password':'secret'}).status_code,200)
        self.client.post(url,{'username':'none','password':'secret'},REMOTE_ADDR='127.0.0.2')
        self.assertEqual(self.client.post(url,{'username':'none','password':'secret'},REMOTE_ADDR='127.0.0.3').status_code,429)
        self.client.post(url,{'username':'one','password':'secret'},REMOTE_ADDR='10.0.0.1');self.client.post(url,{'username':'two','password':'secret'},REMOTE_ADDR='10.0.0.1')
        self.assertEqual(self.client.post(url,{'username':'three','password':'secret'},REMOTE_ADDR='10.0.0.1').status_code,429)
        self.assertNotIn('secret',str(list(AuditLog.objects.values('before','after'))))
    def test_workflow_pages_and_permissions(self):
        self.client.force_login(self.raqa);capa=self.capa();recall=self.recall()
        for name,args in [('task-list',[]),('task-create',[]),('capa-evaluate',[capa.pk]),('recall-ledger',[recall.pk]),('recipient-create',[recall.pk]),('artifact-list',[self.c.pk]),('rule-apply',[self.c.pk])]:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,200,name)
        self.assertEqual(self.client.get(reverse('rule-list')).status_code,200)
        self.client.force_login(self.admin);self.assertEqual(self.client.get(reverse('rule-list')).status_code,200)
    def test_pdf_versions_snapshot_and_access(self):
        font=os.environ.get('PDF_KOREAN_FONT')
        if not font: self.skipTest('PDF_KOREAN_FONT 미설정: 실제 PDF 검증 불가')
        with override_settings(PDF_KOREAN_FONT=font):
            attachment=self.attachment()
            with override_settings(ANTIVIRUS_COMMAND=['scanner']),patch('pms.file_security.subprocess.run') as run:
                run.return_value.returncode=0;scan_attachment(attachment,self.staff)
            first=generate_report(self.c,self.raqa);original=Path(first.file.path).read_bytes()
            self.c.title='변경 제목';self.c.save();second=generate_report(self.c,self.raqa)
        self.assertEqual((first.version,second.version),(1,2));self.assertEqual(first.snapshot['complaint']['title'],'case');self.assertEqual(Path(first.file.path).read_bytes(),original)
        self.assertEqual(first.sha256,hashlib.sha256(original).hexdigest())
        self.client.force_login(self.staff);self.assertEqual(self.client.get(reverse('artifact-download',args=[first.pk])).status_code,403)
        self.client.force_login(self.raqa);response=self.client.get(reverse('artifact-download',args=[first.pk]));self.assertEqual(response.status_code,200);response.close()
        attachment.scan_status='QUARANTINED';attachment.save()
        self.assertEqual(self.client.get(reverse('artifact-download',args=[first.pk])).status_code,403)
    def test_timezone_task_boundary_and_form(self):
        from zoneinfo import ZoneInfo
        self.staff.profile.timezone_name='America/New_York';self.staff.profile.save()
        task=self.task(due_at=timezone.datetime(2026,11,1,6,30,tzinfo=timezone.get_default_timezone()))
        self.client.force_login(self.staff);response=self.client.get(reverse('task-detail',args=[task.pk]))
        self.assertEqual(response.status_code,200)
        with timezone.override(ZoneInfo('America/New_York')):
            from .workflow_forms import TaskForm
            form=TaskForm({'complaint':self.c.pk,'assignee':self.staff.pk,'title':'시간','priority':'NORMAL','status':'WAITING','due_at':'2026-11-01T01:30'})
            self.assertFalse(form.is_valid())  # ambiguous DST wall clock must not be silently chosen
    def test_backup_restore_hashes_and_no_live_overwrite(self):
        import sqlite3,zipfile,json
        from django.core.management.base import CommandError
        source=Path(self.tmp.name)/'source.sqlite3'; media=Path(settings.MEDIA_ROOT);media.mkdir(parents=True)
        (media/'evidence.txt').write_bytes(b'evidence');(media/'report.pdf').write_bytes(b'%PDF-test')
        with sqlite3.connect(source) as db:
            db.execute('CREATE TABLE pms_attachment (id integer primary key, file text)');db.execute("INSERT INTO pms_attachment VALUES (1,'evidence.txt')")
            db.execute('CREATE TABLE pms_reportartifact (id integer primary key,file text,bundle text)');db.execute("INSERT INTO pms_reportartifact VALUES (1,'report.pdf','')")
        db.close()
        archive=Path(self.tmp.name)/'backup.zip';restored=Path(self.tmp.name)/'isolated'
        with patch.dict(settings.DATABASES['default'],{'NAME':str(source)}):
            manifest=backup(archive,quiesced=True);result=restore_verify(archive,restored)
            self.assertEqual(manifest,result['files']);self.assertEqual((restored/'media/evidence.txt').read_bytes(),b'evidence')
            self.assertRaises(CommandError,restore_verify,archive,media)
            self.assertRaises(CommandError,restore_verify,archive,restored)
            self.assertRaises(CommandError,backup,Path(self.tmp.name)/'no.zip',False)
        bad=Path(self.tmp.name)/'tampered.zip'
        with zipfile.ZipFile(archive) as z,zipfile.ZipFile(bad,'w') as w:
            for name in z.namelist(): w.writestr(name,b'tampered' if name=='media/evidence.txt' else z.read(name))
        self.assertRaises(CommandError,restore_verify,bad,Path(self.tmp.name)/'bad-restore')
    def test_html_task_and_evaluation_submissions(self):
        self.client.force_login(self.raqa)
        response=self.client.post(reverse('task-create'),{'complaint':self.c.pk,'assignee':self.staff.pk,'title':'화면 등록','priority':'NORMAL','due_at':'2026-12-01T10:00','status':'WAITING'})
        self.assertEqual(response.status_code,302)
        task=WorkTask.objects.get(title='화면 등록')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('task-edit',args=[task.pk]),{'status':'DONE','assignee':self.other.pk}).status_code,302)
        task.refresh_from_db();self.assertEqual(task.status,'DONE');self.assertEqual(task.assignee,self.staff)
        self.client.force_login(self.raqa);capa=self.capa()
        response=self.client.post(reverse('capa-evaluate',args=[capa.pk]),self.evaluation('FAIL'))
        self.assertEqual(response.status_code,302);self.assertEqual(capa.evaluations.count(),1)
    def test_html_rule_recipient_and_recovery_submissions(self):
        import json
        self.client.force_login(self.admin)
        response=self.client.post(reverse('rule-create'),{'name':'화면 규칙','conditions':'{}','basis':'REPORTED','days':3,'day_type':'BUSINESS','holidays':'[]','effective_on':timezone.localdate().isoformat(),'change_reason':'예시 검증','is_example':'on'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.post(reverse('rule-apply',args=[self.c.pk]),{'name':'화면 규칙','reason':'화면 적용'}).status_code,200)
        self.assertFalse(self.c.rule_applications.exists())
        recall=self.recall();partner=BusinessPartner.objects.create(name='화면 거래처')
        response=self.client.post(reverse('recipient-create',args=[recall.pk]),{'lot':self.lot.pk,'partner':partner.pk,'unit':'개','target_quantity':5,'reply_status':'WAITING'})
        self.assertEqual(response.status_code,302)
        row=recall.recipients.get();url=reverse('recovery-create',args=[row.pk])
        self.assertEqual(self.client.post(url,{'quantity':3,'recovered_on':timezone.localdate().isoformat()}).status_code,302)
        self.assertContains(self.client.post(url,{'quantity':3,'recovered_on':timezone.localdate().isoformat()}),'대상 수량을 초과')
        self.assertEqual(row.recovered_quantity,3)
    def test_postgres_adapter_uses_argv_and_hides_output(self):
        import subprocess
        from django.core.management.base import CommandError
        from .postgres_backup import run_native
        with patch('pms.postgres_backup.subprocess.run') as run:
            run_native(['pg_dump','--format=custom'])
            self.assertTrue(run.call_args.kwargs['check']);self.assertTrue(run.call_args.kwargs['capture_output'])
            run.side_effect=subprocess.CalledProcessError(1,['pg_dump'],stderr='private evidence')
            with self.assertRaises(CommandError) as error: run_native(['pg_dump'])
            self.assertNotIn('private evidence',str(error.exception))


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ConcurrentRecoveryTests(TransactionTestCase):
    def test_concurrent_capacity_is_preserved(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections, OperationalError
        import time
        admin=User.objects.create_superuser('concurrent-admin')
        maker=Manufacturer.objects.create(name='concurrent maker')
        device=MedicalDevice.objects.create(manufacturer=maker,name='device',model_number='c')
        udi=UDI.objects.create(device=device,device_identifier='concurrent-udi')
        lot=ProductLot.objects.create(device=device,udi=udi,lot_number='concurrent-lot')
        recall=Recall.objects.create(title='회수',reason='검증',risk_level='HIGH',device=device,distributed_quantity=10,target_quantity=10,start_date=timezone.localdate(),expected_end_date=timezone.localdate(),owner=admin)
        partner=BusinessPartner.objects.create(name='concurrent partner')
        recipient=RecallRecipient.objects.create(recall=recall,lot=lot,partner=partner,target_quantity=10)
        barrier=Barrier(2)
        def recover():
            barrier.wait()
            try:
                for attempt in range(10):
                    try: record_recovery(recipient,admin,7,timezone.localdate());return 'ok'
                    except ValidationError: return 'capacity'
                    except OperationalError:
                        if attempt==9: raise
                        time.sleep(0.02)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:recover(),range(2)))
        self.assertEqual(sorted(results),['capacity','ok'])
        recipient.refresh_from_db();self.assertEqual(recipient.recovered_total,7);self.assertEqual(recipient.recovered_quantity,7)
