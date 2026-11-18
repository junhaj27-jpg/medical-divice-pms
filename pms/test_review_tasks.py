import hashlib,json,shutil
from pathlib import Path
from uuid import uuid4
from datetime import datetime,date,time,timedelta
from unittest.mock import patch
from django.test import TestCase,TransactionTestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError,PermissionDenied
from . import test_dossier as fixtures
from . import dossier
from . import review_tasks as svc
from .models import Attachment,Notification,ReportingRule,TaskHistory,WorkTask,CAPA,UDI,CustomerComplaint
from .market_models import CaseMarket
from .workflow import tasks_for,notify_tasks,save_task,evaluate_capa
from .review_task_models import ReviewTaskEvidence,ReviewTaskContext
from .regulatory import rule_payload

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReviewTaskTests(TestCase):
    fda=fixtures.DossierTests.fda
    def setUp(self):
        fixtures.DossierTests.setUp(self)
        dossier.validate(self.user,self.revision)
        self.event=dossier.review(self.user,self.revision,'REQUESTED','TEST request',0)
        self.folder=Path.cwd()/'.test-media'/uuid4().hex;self.folder.mkdir(parents=True)
        self.addCleanup(shutil.rmtree,self.folder);self.enterContext(override_settings(MEDIA_ROOT=self.folder))
    def create(self,**kwargs):
        args={'assignee':self.user,'title':'TEST review','criteria':'TEST review source and retain evidence','due_at':(timezone.now()+timedelta(days=1)).isoformat()};args.update(kwargs)
        return svc.create(self.user,'DOCUMENT',self.event.pk,**args)[0]
    def evidence(self,task):
        data=b'TEST synthetic completed RA review evidence';name=uuid4().hex+'.txt';(self.folder/name).write_bytes(data)
        return Attachment.objects.create(ra_profile=task.ra_profile,file=name,original_name='TEST-evidence.txt',uploaded_by=self.user,scan_status='PASSED',sha256=hashlib.sha256(data).hexdigest())
    def update(self,task,action,**kwargs):
        task.refresh_from_db();context=ReviewTaskContext.objects.get(task=task)
        args={'expected':context.version,'action':action,'reason':'TEST reason'};args.update(kwargs)
        return svc.update(self.user,task,**args)
    def test_idempotent_source_and_notification_creation(self):
        first=self.create();second=self.create()
        self.assertEqual(first.pk,second.pk);self.assertEqual(ReviewTaskContext.objects.count(),1)
        self.assertEqual(Notification.objects.filter(work_task=first).count(),2)
    def test_complete_requires_criteria_comment_and_evidence(self):
        task=self.create()
        with self.assertRaises(ValidationError):self.update(task,'complete',comment='TEST checked',criteria_confirmed=True)
        file=self.evidence(task)
        task=self.update(task,'complete',comment='TEST all criteria checked',criteria_confirmed=True,evidence_ids=[file.pk])
        self.assertEqual(task.status,'DONE');self.assertEqual(task.review_context.completed_by,self.user)
        self.assertTrue(task.review_context.completed_at)
    def test_reopen_preserves_prior_completion_and_requires_new_cycle_evidence(self):
        task=self.create();file=self.evidence(task)
        task=self.update(task,'complete',comment='TEST checked',criteria_confirmed=True,evidence_ids=[file.pk])
        task=self.update(task,'reopen');self.assertEqual(task.review_context.cycle,2)
        with self.assertRaises(ValidationError):self.update(task,'complete',comment='TEST checked',criteria_confirmed=True)
        task=self.update(task,'complete',comment='TEST rechecked',criteria_confirmed=True,evidence_ids=[file.pk])
        self.assertEqual(task.review_evidence.count(),2);self.assertGreaterEqual(task.history.count(),4)
    def test_optimistic_conflict_and_due_history(self):
        task=self.create();old_due=task.due_at
        task=self.update(task,'edit',due_at=(old_due+timedelta(days=3)).isoformat(),deadline_mode='MANUAL')
        self.assertEqual(task.review_context.version,2)
        history=task.history.order_by('-pk').first();self.assertEqual(history.before['due_at'],old_due.isoformat());self.assertEqual(history.after['reason'],'TEST reason')
        with self.assertRaises(ValidationError):svc.update(self.user,task,expected=1,action='start',reason='TEST stale')
    def test_assignee_requires_market_source_access(self):
        self.access.markets=[];self.access.save()
        with self.assertRaises(PermissionDenied):self.create()
    def test_revocation_hides_task_notifications_and_download(self):
        task=self.create();file=self.evidence(task);task=self.update(task,'evidence',evidence_ids=[file.pk])
        self.access.markets=[];self.access.save()
        self.assertFalse(tasks_for(self.user).filter(pk=task.pk).exists())
        for path in [reverse('market-task-detail',args=[task.pk]),reverse('market-review-task-api',args=[task.pk]),reverse('market-review-task-evidence',args=[task.pk,task.review_evidence.get().pk])]:self.assertEqual(self.client.get(path).status_code,404)
        self.assertFalse(self.client.get(reverse('market-review-notifications-api')).json()['items'])
    def test_review_change_notifications_and_read_state(self):
        task=self.create();task=self.update(task,'request_changes',comment='TEST fix')
        notice=Notification.objects.filter(work_task=task,dedupe_key__contains='CHANGES_REQUESTED').get()
        url=reverse('market-review-notification-read-api',args=[notice.pk])
        self.assertEqual(self.client.post(url).status_code,200)
        notice.refresh_from_db();self.assertTrue(notice.read_at)
        self.client.force_login(self.other);self.assertEqual(self.client.post(url).status_code,404)
    def test_existing_notify_command_deduplicates_due_conditions(self):
        task=self.create();now=timezone.now();self.assertEqual(notify_tasks(now),1);self.assertEqual(notify_tasks(now),0)
        self.assertEqual(notify_tasks(task.due_at+timedelta(seconds=1)),1)
    def test_legacy_editor_cannot_bypass_evidence_and_reason(self):
        task=self.create();task.status='DONE'
        with self.assertRaises(ValidationError):save_task(task,self.user)
        self.assertEqual(self.client.get(reverse('task-edit',args=[task.pk])).status_code,403)
    def test_filters_and_json_update(self):
        task=self.create();response=self.client.get(reverse('market-my-tasks-api'),{'product':self.device.pk,'status':'WAITING'})
        self.assertEqual(response.status_code,200);self.assertIn(task.pk,[r['id'] for r in response.json()['items']])
        response=self.client.post(reverse('market-review-task-api',args=[task.pk]),json.dumps({'action':'start','expected':1,'reason':'TEST start'}),content_type='application/json')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['version'],2)
    def test_rule_business_calendar_is_frozen_and_case_dates_unchanged(self):
        rule=ReportingRule.objects.create(name='TEST task calendar',version=1,conditions={},basis='CUSTOM',days=2,day_type='BUSINESS',include_start=False,deadline_unit='DAYS',deadline_time=time(17),timezone_name='Europe/Berlin',jurisdiction='US',effective_on=date(2026,1,1),holidays=[{'date':'2026-11-16','name':'TEST holiday'}],holiday_verified_from=date(2026,1,1),holiday_verified_until=date(2026,12,31),holiday_checked_on=date(2026,11,1),change_reason='TEST example')
        rule._workflow_write=True;rule.state='APPROVED';rule.approved_by=self.user;rule.save()
        rule.changes.create(actor=self.user,action='RULE_APPROVE',reason='TEST fixture',after=rule_payload(rule))
        task=self.create(deadline_mode='RULE',basis_at='2026-11-13T09:00:00+01:00',rule_id=rule.pk)
        self.assertEqual(task.due_at.date(),date(2026,11,18))
        self.assertEqual(task.review_context.deadline_snapshot['calculation']['version'],1)
        self.assertEqual(len(task.review_context.deadline_snapshot['calculation']['excluded']),3)
    def test_unapproved_rule_refused(self):
        rule=ReportingRule.objects.create(name='TEST pending',change_reason='TEST')
        with self.assertRaises(ValidationError):self.create(deadline_mode='RULE',basis_at=timezone.now().isoformat(),rule_id=rule.pk)
    def test_source_change_task_snapshot_and_deduplication(self):
        revision=fixtures.DossierTests.link(self)
        self.fda('TEST-v2','TEST amended scope')
        item=dossier.impacts(self.user,revision)[0]
        values={'assignee':self.user,'title':'TEST impact','criteria':'TEST assess clauses','due_at':timezone.now().isoformat(),'section':item['section'],'source_fingerprint':item['fingerprint']}
        task,_=svc.create(self.user,'IMPACT',revision.pk,**values)
        same,created=svc.create(self.user,'IMPACT',revision.pk,**values)
        self.assertFalse(created);self.assertEqual(task.pk,same.pk)
        self.assertIn('before',task.review_context.source_snapshot);self.assertIn('after',task.review_context.source_snapshot)
        response=self.client.get(reverse('market-review-task-detail',args=[task.pk]))
        self.assertContains(response,'TEST-v1');self.assertContains(response,'TEST-v2')
    def test_capa_existing_followup_is_reused(self):
        udi=UDI.objects.create(device=self.device,device_identifier='TEST-task-UDI')
        case=CustomerComplaint.objects.create(device=self.device,udi=udi,reporter=self.user,title='TEST',complaint_type='TEST',description='TEST',occurred_on=date(2026,1,1),is_example=True)
        CaseMarket.objects.create(complaint=case,market='US')
        capa=CAPA.objects.create(complaint=case,title='TEST CAPA',corrective_action='TEST',owner=self.user,due_date=date(2026,11,20))
        ev=evaluate_capa(capa,self.user,{'action_result':'TEST','criteria':'TEST','scheduled_on':date(2026,11,18),'evaluated_on':date(2026,11,18),'verdict':'FAIL','rationale':'TEST'})
        task,created=svc.create(self.user,'CAPA',ev.pk,assignee=self.user,title='TEST CAPA review',criteria='TEST evidence',country='US',due_at=timezone.now().isoformat())
        self.assertEqual(task.pk,ev.followup_id);self.assertEqual(WorkTask.objects.filter(capa=capa).count(),1)

    def test_legacy_notification_backfill_preserves_content_and_timestamp(self):
        from importlib import import_module
        from django.apps import apps
        task=self.create()
        notice=Notification.objects.create(user=self.user,title='TEST legacy',message='TEST retained',dedupe_key=f'task:{task.pk}:{self.user.pk}:TEST:SOON')
        before=(notice.title,notice.message,notice.created_at,notice.updated_at)
        import_module('pms.migrations.0053_notification_work_task_reviewtaskcontext_and_more').link_existing_task_notices(apps,None)
        notice.refresh_from_db();self.assertEqual(notice.work_task_id,task.pk)
        self.assertEqual((notice.title,notice.message,notice.created_at,notice.updated_at),before)

    def test_capa_reevaluation_links_previous_review_task(self):
        udi=UDI.objects.create(device=self.device,device_identifier='TEST-task-capa-chain')
        case=CustomerComplaint.objects.create(device=self.device,udi=udi,reporter=self.user,title='TEST',complaint_type='TEST',description='TEST',occurred_on=date(2026,1,1),is_example=True)
        CaseMarket.objects.create(complaint=case,market='US')
        capa=CAPA.objects.create(complaint=case,title='TEST CAPA chain',corrective_action='TEST',owner=self.user,due_date=date(2026,11,20))
        data={'action_result':'TEST','criteria':'TEST','scheduled_on':date(2026,11,18),'evaluated_on':date(2026,11,18),'verdict':'FAIL','rationale':'TEST'}
        first=evaluate_capa(capa,self.user,data)
        prior,_=svc.create(self.user,'CAPA',first.pk,assignee=self.user,title='TEST first',criteria='TEST',country='US',due_at=timezone.now().isoformat())
        second=evaluate_capa(capa,self.user,data)
        following,_=svc.create(self.user,'CAPA',second.pk,assignee=self.user,title='TEST next',criteria='TEST',country='US',due_at=timezone.now().isoformat())
        self.assertNotEqual(prior.pk,following.pk);self.assertEqual(following.review_context.parent_task_id,prior.pk)
    def test_quarantined_and_tampered_evidence_cannot_complete(self):
        task=self.create();file=self.evidence(task)
        file.scan_status='QUARANTINED';file.save()
        with self.assertRaises(ValidationError):self.update(task,'complete',comment='TEST checked',criteria_confirmed=True,evidence_ids=[file.pk])
        file.scan_status='PASSED';file.save();(self.folder/str(file.file)).write_bytes(b'TEST tampered')
        with self.assertRaises(PermissionDenied):self.update(task,'complete',comment='TEST checked',criteria_confirmed=True,evidence_ids=[file.pk])

    def test_capa_access_reuses_case_market_when_registration_is_missing(self):
        from .market_models import ProductMarket
        udi=UDI.objects.create(device=self.device,device_identifier='TEST-task-capa-unregistered')
        case=CustomerComplaint.objects.create(device=self.device,udi=udi,reporter=self.user,title='TEST',complaint_type='TEST',description='TEST',occurred_on=date(2026,1,1),is_example=True)
        CaseMarket.objects.create(complaint=case,market='US')
        capa=CAPA.objects.create(complaint=case,title='TEST CAPA',corrective_action='TEST',owner=self.user,due_date=date(2026,11,20))
        data={'action_result':'TEST','criteria':'TEST','scheduled_on':date(2026,11,18),'evaluated_on':date(2026,11,18),'verdict':'FAIL','rationale':'TEST'}
        ev=evaluate_capa(capa,self.user,data)
        ProductMarket.objects.filter(device=self.device).delete()
        task,_=svc.create(self.user,'CAPA',ev.pk,assignee=self.user,title='TEST',criteria='TEST',country='US',due_at=timezone.now().isoformat())
        self.assertTrue(svc.accessible(self.user,task.review_context))
    def test_upload_without_scanner_stays_unusable_for_completion(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        task=self.create()
        with override_settings(ANTIVIRUS_COMMAND=[]):
            response=self.client.post(reverse('market-review-task-api',args=[task.pk]),{'action':'upload','file':SimpleUploadedFile('TEST.txt',b'TEST internal example text')})
        self.assertEqual(response.status_code,201);self.assertEqual(response.json()['scan_status'],'FAILED')
        with self.assertRaises(ValidationError):self.update(task,'complete',comment='TEST',criteria_confirmed=True,evidence_ids=[response.json()['attachment_id']])


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReviewTaskConcurrencyTests(TransactionTestCase):
    fda=fixtures.DossierTests.fda
    def test_two_writers_do_not_overwrite_each_other(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections,connection
        if connection.settings_dict['NAME']==':memory:' or 'mode=memory' in str(connection.settings_dict['NAME']):self.skipTest('Use SQLITE_TEST_PATH for real writer-lock verification')
        fixtures.DossierTests.setUp(self)
        dossier.validate(self.user,self.revision)
        event=dossier.review(self.user,self.revision,'REQUESTED','TEST',0)
        task,_=svc.create(self.user,'DOCUMENT',event.pk,assignee=self.user,title='TEST concurrent',criteria='TEST criteria',due_at=timezone.now().isoformat())
        barrier=Barrier(2)
        def writer(index):
            from django.contrib.auth import get_user_model
            try:
                actor=get_user_model().objects.get(pk=self.user.pk);local=WorkTask.objects.get(pk=task.pk)
                barrier.wait()
                try:svc.update(actor,local,expected=1,action='start',reason='TEST writer '+str(index));return 'saved'
                except ValidationError:return 'conflict'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(writer,[1,2]))
        self.assertEqual(sorted(results),['conflict','saved'])
        self.assertEqual(ReviewTaskContext.objects.get(task=task).version,2)
        self.assertEqual(task.history.count(),2)
