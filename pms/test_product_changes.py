import hashlib,json,shutil,uuid
from pathlib import Path
from datetime import date,timedelta
from django.test import TestCase,TransactionTestCase,override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError,PermissionDenied
from django.utils import timezone
from . import test_dossier as fixtures
from .models import MedicalDevice,Attachment,WorkTask,ControlledDocument,RegulatoryProfile,BusinessPartner
from .market_models import ProductMarket
from .mri_models import MRIConfiguration
from .dental_models import DentalProject,WritingTemplate
from .product_change_models import MRIProductChange,MRIChangeMarket,MRIChangeAction
from . import product_changes as svc
from . import review_tasks
from .ra_services import save_record

class ChangeFixtures:
    fda=fixtures.DossierTests.fda
    def setup_change(self):
        fixtures.DossierTests.setUp(self)
        self.device.product_type='MRI';self.device.save()
        self.config=MRIConfiguration.objects.create(device=self.device,family=self.device,version=1,configuration_name='DEMO config',intended_use='DEMO use',target_population='DEMO adults',users='TEST clinicians',environment='TEST clinic',software_version='DEMO-SW-1',is_example=True,recorded_by=self.user)
        ProductMarket.objects.create(device=self.device,market='DE',identifier='TEST-DE-001',is_example=True)
        template=WritingTemplate.objects.create(key='test-eu-change',name='TEST EU checklist',market='EU',state='DRAFT',checked_on=date(2026,11,19),conditions={'internal_collection':True},items=self.template.items)
        template.state='REVIEW';template.save();template.state='PUBLISHED';template.save()
        self.eu_project=DentalProject.objects.create(device=self.device,market='EU',template=template,guide=self.project.guide,specification=self.project.specification)
        self.folder=Path.cwd()/'.test-media'/uuid.uuid4().hex;self.folder.mkdir(parents=True);self.addCleanup(shutil.rmtree,self.folder)
        self.enterContext(override_settings(MEDIA_ROOT=self.folder))
    def submit(self,**kwargs):
        values={'kind':'SOFTWARE','before_value':'DEMO-SW-1','after_value':'DEMO-SW-2','reason':'TEST changed algorithm labeling references require review','planned_on':date(2026,12,1),'countries':['US','DE'],'request_key':uuid.uuid4()};values.update(kwargs)
        return svc.submit(self.user,self.device,**values)[0]
    def decide(self,review,flags=None,complete=False):
        review.refresh_from_db();flags=flags or ['DOCUMENT']
        targets={'documents':[review.snapshot['documents'][0]['key']] if 'DOCUMENT' in flags else [],'evidence':[review.snapshot['evidence'][0]['key']] if 'EVIDENCE' in flags else []}
        return svc.decide(self.user,review,expected=review.version,decisions=flags,targets=targets,rationale='TEST reason with no submission conclusion',complete=complete)
    def create_task(self,review,kind='DOCUMENT',**kwargs):
        key=review.snapshot['documents' if kind=='DOCUMENT' else 'evidence'][0]['key']
        values={'assignee':self.user,'title':'TEST product change follow-up','criteria':'TEST revise and attach reviewed proof','due_at':(timezone.now()+timedelta(days=2)).isoformat()};values.update(kwargs)
        return svc.create_task(self.user,review,action_type=kind,target_key=key,**values)[0]
    def proof(self,task):
        data=b'TEST trusted synthetic result';name=uuid.uuid4().hex+'.txt';(self.folder/name).write_bytes(data)
        return Attachment.objects.create(ra_profile=task.ra_profile,file=name,original_name='TEST.txt',uploaded_by=self.user,sha256=hashlib.sha256(data).hexdigest(),scan_status='PASSED')
    def finish_task(self,task):
        file=self.proof(task)
        task=review_tasks.update(self.user,task,expected=task.review_context.version,action='complete',reason='TEST verified result',comment='TEST criteria checked',criteria_confirmed=True,evidence_ids=[file.pk])
        return task,file

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProductChangeTests(ChangeFixtures,TestCase):
    def setUp(self):self.setup_change()
    def test_software_and_label_requests_do_not_modify_master(self):
        change=self.submit();label=self.submit(kind='LABEL',before_value='TEST LABEL v1',after_value='TEST LABEL v2')
        self.assertEqual(change.market_reviews.count(),2);self.assertEqual(label.kind,'LABEL')
        self.assertEqual(self.device.mri_configurations.first().software_version,'DEMO-SW-1')
        self.assertEqual(ProductMarket.objects.get(device=self.device,market='DE').identifier,'TEST-DE-001')
    def test_request_idempotency(self):
        key=uuid.uuid4();first=self.submit(request_key=key);second=self.submit(request_key=key)
        self.assertEqual(first.pk,second.pk)
        with self.assertRaises(ValidationError):self.submit(request_key=key,after_value='DEMO-SW-3')
    def test_registered_baseline_must_match(self):
        with self.assertRaises(ValidationError):self.submit(before_value='wrong')
    def test_immutable_snapshot_after_product_and_market_edit(self):
        change=self.submit();review=change.market_reviews.get(country='DE');before=json.dumps(review.snapshot,sort_keys=True)
        self.device.name='TEST new product name';self.device.save()
        ProductMarket.objects.filter(device=self.device,market='DE').update(identifier='TEST changed registration')
        config={field.name:getattr(self.config,field.name) for field in self.config._meta.fields if field.name not in ('id','recorded_at')}
        config.update(version=2,software_version='DEMO-SW-9');MRIConfiguration.objects.create(**config)
        change.refresh_from_db();review.refresh_from_db()
        self.assertEqual(change.product_snapshot['configuration']['software_version'],'DEMO-SW-1');self.assertEqual(json.dumps(review.snapshot,sort_keys=True),before)
        review.snapshot={}
        with self.assertRaises(ValidationError):review.save()
    def test_market_permission_on_screen_api_task_and_original(self):
        change=self.submit();us=change.market_reviews.get(country='US');de=change.market_reviews.get(country='DE')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('market-product-change-review',args=[us.pk])).status_code,200)
        for name in ['market-product-change-review','market-product-change-review-api','market-product-change-task','market-product-change-task-api']:
            self.assertEqual(self.client.get(reverse(name,args=[de.pk])).status_code,404)
        root=self.client.get(reverse('market-product-change-api',args=[change.pk])).json()
        self.assertEqual([r['country'] for r in root['reviews']],['US'])
        key=de.snapshot['documents'][0]['key']
        self.assertEqual(self.client.get(reverse('market-product-change-candidate-api',args=[de.pk,key])).status_code,404)
    def test_market_decisions_are_independent_and_flags_combine(self):
        change=self.submit();us=change.market_reviews.get(country='US');de=change.market_reviews.get(country='DE')
        self.decide(us,['DOCUMENT','EVIDENCE']);self.decide(de,['NONE'],True)
        us.refresh_from_db();de.refresh_from_db();self.assertEqual(us.status,'IN_REVIEW');self.assertEqual(de.status,'COMPLETED')
        self.assertEqual(set(us.decisions.get().decisions),{'DOCUMENT','EVIDENCE'})
    def test_no_impact_exclusive_and_rationale_required(self):
        review=self.submit().market_reviews.get(country='US')
        with self.assertRaises(ValidationError):svc.decide(self.user,review,expected=1,decisions=['NONE','DOCUMENT'],targets={},rationale='TEST')
        with self.assertRaises(ValidationError):svc.decide(self.user,review,expected=1,decisions=['NONE'],targets={},rationale='')
    def test_missing_or_unfinished_actions_block_market_completion(self):
        review=self.submit().market_reviews.get(country='US');self.decide(review)
        with self.assertRaises(ValidationError):self.decide(review,complete=True)
        task=self.create_task(review)
        with self.assertRaises(ValidationError):self.decide(review,complete=True)
        self.finish_task(task);self.decide(review,complete=True);review.refresh_from_db();self.assertEqual(review.status,'COMPLETED')
    def test_action_deduplication_and_task_permissions(self):
        review=self.submit().market_reviews.get(country='US');self.decide(review)
        first=self.create_task(review);second=self.create_task(review);self.assertEqual(first.pk,second.pk)
        self.assertEqual(MRIChangeAction.objects.count(),1)
        self.access.markets=['DE'];self.access.save()
        self.assertEqual(self.client.get(reverse('market-review-task-api',args=[first.pk])).status_code,404)
    def test_completed_task_is_separate_from_market_completion_and_reopening(self):
        review=self.submit().market_reviews.get(country='US');self.decide(review)
        task,_=self.finish_task(self.create_task(review));review.refresh_from_db();self.assertEqual(review.status,'IN_REVIEW')
        self.decide(review,complete=True)
        with self.assertRaises(ValidationError):review_tasks.update(self.user,task,expected=task.review_context.version,action='reopen',reason='TEST reopen')
        self.decide(review,complete=False)
        task=review_tasks.update(self.user,task,expected=task.review_context.version,action='reopen',reason='TEST reopen after market review')
        self.assertEqual(task.status,'IN_PROGRESS')
        with self.assertRaises(ValidationError):self.decide(review,complete=True)
        self.assertTrue(review.decisions.filter(complete=True).exists())
    def test_failed_evidence_blocked_at_request_task_and_review_completion(self):
        review=self.submit().market_reviews.get(country='US');self.decide(review);task=self.create_task(review);file=self.proof(task)
        file.scan_status='QUARANTINED';file.save()
        with self.assertRaises(ValidationError):self.submit(evidence_ids=[file.pk])
        with self.assertRaises(ValidationError):review_tasks.update(self.user,task,expected=1,action='complete',reason='TEST',comment='TEST',criteria_confirmed=True,evidence_ids=[file.pk])
        file.scan_status='PASSED';file.save();task=review_tasks.update(self.user,task,expected=1,action='complete',reason='TEST',comment='TEST',criteria_confirmed=True,evidence_ids=[file.pk])
        file.scan_status='QUARANTINED';file.save()
        with self.assertRaises(PermissionDenied):self.decide(review,complete=True)
    def test_optimistic_market_decision_conflict(self):
        review=self.submit().market_reviews.get(country='US');self.decide(review,['NONE'])
        with self.assertRaises(ValidationError):svc.decide(self.user,review,expected=1,decisions=['NONE'],targets={},rationale='TEST stale')
    def test_screen_api_flow_and_missing_evidence_notice(self):
        response=self.client.post(reverse('market-product-changes-api',args=[self.device.pk]),json.dumps({'kind':'LABEL','before_value':'TEST label 1','after_value':'TEST label 2','reason':'TEST label warning change','planned_on':'2026-12-01','countries':['US','DE'],'request_key':str(uuid.uuid4())}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        change=MRIProductChange.objects.get(pk=response.json()['change_id']);review=change.market_reviews.get(country='DE')
        response=self.client.get(reverse('market-product-change-review',args=[review.pk]));self.assertContains(response,'증빙 확인 필요')
        api=reverse('market-product-change-review-api',args=[review.pk]);response=self.client.post(api,json.dumps({'expected':1,'decisions':['NONE'],'document_targets':[],'evidence_targets':[],'rationale':'TEST reviewed no impact','action':'complete'}),content_type='application/json')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['status'],'COMPLETED')
    def test_frozen_document_and_eu_attachment_remain_accessible_with_scope(self):
        profile=review_tasks.ensure_profile(self.user,self.device,'EU')
        data=b'TEST EU product evidence v1';path=uuid.uuid4().hex+'.txt';(self.folder/path).write_bytes(data)
        file=Attachment.objects.create(ra_profile=profile,file=path,original_name='TEST-EU.txt',uploaded_by=self.user,scan_status='PASSED',sha256=hashlib.sha256(data).hexdigest())
        document=save_record(ControlledDocument(),self.user,{'profile':profile,'owner':self.user,'is_example':profile.is_example,'title':'TEST EU document','category':'TECHNICAL','number':'TEST-EU','version':1,'primary_file':file,'change_reason':'TEST original'},'TEST original')
        change=self.submit(evidence_ids=[file.pk]);review=change.market_reviews.get(country='DE');key=f'document:{document.pk}'
        response=self.client.get(reverse('market-product-change-file',args=[review.pk,key]));self.assertEqual(b''.join(response.streaming_content),data)
        self.decide(review);task=self.create_task(review)
        self.assertIn(file.pk,review_tasks.files_for(task).values_list('pk',flat=True))
        extra=b'TEST EU completion proof created after request';extra_path=uuid.uuid4().hex+'.txt';(self.folder/extra_path).write_bytes(extra)
        updated_file=Attachment.objects.create(ra_profile=profile,file=extra_path,original_name='TEST-new-EU-proof.txt',uploaded_by=self.user,scan_status='PASSED',sha256=hashlib.sha256(extra).hexdigest())
        self.assertIn(updated_file.pk,review_tasks.files_for(task).values_list('pk',flat=True))
        self.assertNotIn(updated_file.pk,[r.get('attachment_id') for r in review.snapshot['evidence']])
        revision=save_record(ControlledDocument(),self.user,{'profile':profile,'owner':self.user,'is_example':profile.is_example,'title':'TEST EU revised','category':'TECHNICAL','number':'TEST-EU','version':2,'primary_file':file,'supersedes':document,'change_reason':'TEST revision'},'TEST revision')
        row=self.client.get(reverse('market-product-change-candidate-api',args=[review.pk,key])).json()['candidate'];self.assertEqual(row['version'],1)
        self.client.force_login(self.other);self.assertEqual(self.client.get(reverse('market-product-change-file',args=[review.pk,key])).status_code,404)

    def test_private_draft_sources_are_redacted_and_cannot_be_opened(self):
        from copy import deepcopy
        from . import test_source_search as search_fixtures
        from .source_search import search
        from . import dossier
        document,folder=search_fixtures.SourceSearchTests.private_document(self)
        result=search(self.user,'PRIVATE UNIQUE',mode='keyword')
        source=next(row for row in result['results'] if row['kind']=='regulation' and row['document_id']==document.pk)
        snapshot=deepcopy(self.revision.draft.snapshot);snapshot['rows'][0]['search_references']=[source]
        revision=dossier.save_revision(self.user,self.revision.document,snapshot,'TEST private source',1)
        review=self.submit().market_reviews.get(country='US');key=f'draft:{revision.draft_id}'
        self.client.force_login(self.other)
        response=self.client.get(reverse('market-product-change-review-api',args=[review.pk]))
        row=next(r for r in response.json()['snapshot']['documents'] if r['key']==key)
        self.assertTrue(row['restricted']);self.assertNotIn('snapshot_hash',row)
        self.assertEqual(self.client.get(reverse('market-product-change-candidate-api',args=[review.pk,key])).status_code,403)
    def test_malformed_api_json_returns_validation_error(self):
        response=self.client.post(reverse('market-product-changes-api',args=[self.device.pk]),'{',content_type='application/json')
        self.assertEqual(response.status_code,400)

    def test_completed_market_reuses_existing_completed_task(self):
        review=self.submit().market_reviews.get(country='US');self.decide(review)
        original=self.create_task(review);self.finish_task(original);self.decide(review,complete=True)
        again=self.create_task(review)
        self.assertEqual(again.pk,original.pk);self.assertEqual(again.status,'DONE')
        self.assertEqual(review.actions.count(),1)
    def test_combined_document_and_evidence_actions_both_must_finish(self):
        review=self.submit().market_reviews.get(country='US');self.decide(review,['DOCUMENT','EVIDENCE'])
        document=self.create_task(review,'DOCUMENT');self.finish_task(document)
        with self.assertRaises(ValidationError):self.decide(review,['DOCUMENT','EVIDENCE'],complete=True)
        evidence=self.create_task(review,'EVIDENCE')
        with self.assertRaises(ValidationError):self.decide(review,['DOCUMENT','EVIDENCE'],complete=True)
        self.finish_task(evidence);self.decide(review,['DOCUMENT','EVIDENCE'],complete=True)
        review.refresh_from_db();self.assertEqual(review.status,'COMPLETED')
    def test_no_impact_correction_does_not_discard_pending_required_tasks(self):
        review=self.submit().market_reviews.get(country='US');self.decide(review)
        task=self.create_task(review);self.decide(review,['NONE'])
        with self.assertRaises(ValidationError):self.decide(review,['NONE'],complete=True)
        self.finish_task(task);self.decide(review,['NONE'],complete=True)
        self.assertEqual(review.actions.count(),1)

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProductChangeConcurrencyTests(ChangeFixtures,TransactionTestCase):
    def test_duplicate_task_creation_from_two_requests(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connection,connections
        from django.contrib.auth import get_user_model
        if 'mode=memory' in str(connection.settings_dict['NAME']) or connection.settings_dict['NAME']==':memory:':self.skipTest('File SQLite/PostgreSQL required')
        self.setup_change();review=self.submit().market_reviews.get(country='US');self.decide(review);barrier=Barrier(2)
        def worker(index):
            try:
                actor=get_user_model().objects.get(pk=self.user.pk);local=MRIChangeMarket.objects.select_related('change__device').get(pk=review.pk)
                barrier.wait()
                task,created=svc.create_task(actor,local,action_type='DOCUMENT',target_key=local.snapshot['documents'][0]['key'],assignee=actor,title='TEST concurrent',criteria='TEST',due_at=timezone.now().isoformat())
                return task.pk,created
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,[1,2]))
        self.assertEqual(len({pk for pk,_ in results}),1);self.assertEqual(sum(created for _,created in results),1);self.assertEqual(MRIChangeAction.objects.count(),1)
