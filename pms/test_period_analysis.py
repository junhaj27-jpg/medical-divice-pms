"""Synthetic aggregate cohorts; no external services or patient identifiers."""
import csv, io, json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date, timedelta
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import Manufacturer,MedicalDevice,UDI,CustomerComplaint,AdverseEvent,Profile,WorkTask
from .market_models import ProductMarket,CaseMarket,MarketAccess
from .period_models import PMSPeriodSnapshot,PMSPeriodAction
from . import period_analysis as svc
from . import review_tasks

class Fixtures:
    def setup_period(self):
        self.user=get_user_model().objects.create_user('TEST-period-ra')
        Profile.objects.create(user=self.user,role='RA_QA')
        self.access=MarketAccess.objects.create(user=self.user,markets=['US','DE'])
        self.device=MedicalDevice.objects.create(name='DEMO MRI periods',model_number='DEMO-PERIOD-MRI',manufacturer=Manufacturer.objects.create(name='DEMO period'))
        self.udi=UDI.objects.create(device=self.device,device_identifier='DEMO-PERIOD-UDI')
        for market in ['US','DE']:ProductMarket.objects.create(device=self.device,market=market,is_example=True)
        self.case('2026-09-01','A1',adverse=True);self.case('2026-09-30','A2')
        self.case('2026-10-01','B1',adverse=True);self.case('2026-10-15','B2');self.case('2026-10-31','B3',adverse=True)
        self.case('2026-08-31','outside');self.case('2026-11-01','outside2')
        self.case('2026-10-02','UNASSIGNED',market=None)
        self.case('2026-10-03','US ONLY',market='US')
        self.client.force_login(self.user)
    def case(self,at,title,adverse=False,market='DE',**kwargs):
        c=CustomerComplaint.objects.create(device=self.device,udi=self.udi,complaint_type='OPTICAL',title='DEMO '+title,description='PRIVATE NARRATIVE DO NOT EXPORT',occurred_on=at,reported_on=at,reporter=self.user,is_example=True,**kwargs)
        if market:CaseMarket.objects.create(complaint=c,market=market)
        if adverse:AdverseEvent.objects.create(complaint=c,event_type='THERMAL',outcome='DEMO',serious=True,narrative='PRIVATE AE TEXT')
        return c
    def data(self,**changes):
        data={'device':self.device,'market':'DE','basis':'reported_on','a_start':date(2026,9,1),'a_end':date(2026,9,30),'b_start':date(2026,10,1),'b_end':date(2026,10,31),'example':'sample','complaint_type':'','display_timezone':'Asia/Seoul'};data.update(changes);return data
    def analysis(self,**changes):return svc.compare(self.user,self.data(**changes))
    def snapshot(self):
        c,r=self.analysis();return svc.save_preview(self.user,svc.preview_token(self.user,c,r))
    def task(self,snapshot,**changes):
        values={'assignee':self.user,'title':'DEMO investigation','criteria':'DEMO check aggregate and attach proof','due_at':(timezone.now()+timedelta(days=3)).isoformat()};values.update(changes)
        return svc.create_task(self.user,snapshot,'INVESTIGATION',**values)
    def metric(self,result,name='complaints'):return next(r for r in result['rows'] if r['metric']==name)

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PeriodAnalysisTests(Fixtures,TestCase):
    def setUp(self):self.setup_period()
    def test_boundaries_unique_market_and_adverse_subset(self):
        c,r=self.analysis();self.assertEqual(self.metric(r),{'metric':'complaints','a':2,'b':3,'delta':1,'percent':50.0})
        self.assertEqual((self.metric(r,'adverse_events')['a'],self.metric(r,'adverse_events')['b']),(1,2))
        CaseMarket.objects.create(complaint=CustomerComplaint.objects.get(title='DEMO B1'),market='US')
        self.assertEqual(self.metric(self.analysis()[1])['b'],3)
        self.assertEqual(r['days'],{'a':30,'b':31});self.assertIsNone(r['quality']['unassigned_excluded'])
    def test_zero_baseline_and_negative_delta(self):
        c,r=self.analysis(a_start=date(2026,7,1),a_end=date(2026,7,31));self.assertIsNone(self.metric(r)['percent']);self.assertEqual(self.metric(r)['delta'],3)
        c,r=self.analysis(a_start=date(2026,10,1),a_end=date(2026,10,31),b_start=date(2026,9,1),b_end=date(2026,9,30));self.assertEqual(self.metric(r)['delta'],-1)
        snap=svc.save_preview(self.user,svc.preview_token(self.user,c,r));rows=list(csv.DictReader(io.StringIO(svc.export_csv(snap).decode('utf-8-sig'))))
        self.assertEqual(next(row for row in rows if row['metric']=='complaints')['delta_count'],'-1')
    def test_date_basis_same_filters_and_timezone_invariance(self):
        case=CustomerComplaint.objects.get(title='DEMO B1');case.occurred_on=date(2026,9,30);case.save()
        one=self.analysis(basis='occurred_on')[1];two=self.analysis(basis='occurred_on',display_timezone='America/New_York')[1]
        self.assertEqual(one['rows'],two['rows']);self.assertEqual(self.metric(one)['a'],3)
        self.assertEqual(self.metric(self.analysis(complaint_type='MISSING')[1])['b'],0)
    def test_exclusions_unassigned_count_only_with_global_access(self):
        self.access.delete();self.user.refresh_from_db();self.case('2026-10-04','UNKNOWN MARKET',market='XX');c,r=self.analysis();self.assertEqual(r['quality']['unassigned_excluded'],{'a':0,'b':2})
        self.assertEqual(self.metric(r)['b'],3)
    def test_snapshot_immutable_after_source_edit_and_fresh_reanalysis(self):
        c,r=self.analysis();token=svc.preview_token(self.user,c,r)
        case=CustomerComplaint.objects.get(title='DEMO B1');case.reported_on=date(2026,11,2);case.save()
        snap=svc.save_preview(self.user,token);self.assertEqual(self.metric(snap.result)['b'],3)
        self.assertEqual(svc.save_preview(self.user,token).pk,snap.pk)
        fresh=self.snapshot();self.assertNotEqual(fresh.pk,snap.pk);self.assertEqual(self.metric(fresh.result)['b'],2)
        snap.result={}
        with self.assertRaises(ValidationError):snap.save()
    def test_detail_csv_frozen_parity_privacy_and_utf8_bom(self):
        snap=self.snapshot();self.device.name='REVISED NAME';self.device.save()
        detail=self.client.get(reverse('market-pms-snapshot-api',args=[snap.pk])).json()
        response=self.client.get(reverse('market-pms-csv',args=[snap.pk]));self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        text=response.content.decode('utf-8-sig');self.assertNotIn('PRIVATE',text);self.assertNotIn('REVISED NAME',text)
        rows=list(csv.DictReader(io.StringIO(text)))
        self.assertEqual([(row['metric'],int(row['a_count']),int(row['b_count'])) for row in rows],[(row['metric'],row['a'],row['b']) for row in detail['result']['rows']])
        html=self.client.get(reverse('market-pms-snapshot',args=[snap.pk]));self.assertContains(html,'계산 시각')
    def test_empty_results_csv_and_overlap_warning(self):
        c,r=self.analysis(complaint_type='NONE',b_start=date(2026,9,1),b_end=date(2026,9,30))
        self.assertTrue(all(row['a']==row['b']==0 for row in r['rows']));self.assertTrue(any('겹칩니다' in w for w in r['warnings']))
        snap=svc.save_preview(self.user,svc.preview_token(self.user,c,r));self.assertIn(',,',svc.export_csv(snap).decode('utf-8-sig'))
    def test_screen_api_list_save_csv_and_task_permissions_revoked(self):
        snap=self.snapshot();self.access.markets=['US'];self.access.save()
        for name in ['market-pms-snapshot','market-pms-snapshot-api','market-pms-csv']:
            self.assertEqual(self.client.get(reverse(name,args=[snap.pk])).status_code,404)
        for name in ['market-pms-task','market-pms-task-api']:
            self.assertEqual(self.client.post(reverse(name,args=[snap.pk,'INVESTIGATION']),{}).status_code,404)
        self.assertEqual(self.client.get(reverse('market-pms-snapshots-api')).json()['items'],[])
        with self.assertRaises(PermissionDenied):self.analysis()
        c=snap.criteria;r=snap.result;token=svc.preview_token(self.user,c,r)
        self.assertEqual(self.client.post(reverse('market-pms-compare-api'),{'action':'save','token':token}).status_code,403)
    def test_product_market_exact_pair_and_staff_denied(self):
        other=MedicalDevice.objects.create(name='TEST other',model_number='DEMO-OTHER',manufacturer=self.device.manufacturer)
        ProductMarket.objects.create(device=other,market='US')
        with self.assertRaises(PermissionDenied):svc.compare(self.user,self.data(device=other,market='DE'))
        self.user.profile.role='STAFF';self.user.profile.save()
        self.assertEqual(self.client.get(reverse('market-pms-compare')).status_code,403)
    def test_signed_preview_cannot_be_tampered_or_shared(self):
        c,r=self.analysis();token=svc.preview_token(self.user,c,r)
        with self.assertRaises(ValidationError):svc.save_preview(self.user,token+'x')
        other=get_user_model().objects.create_user('TEST other');Profile.objects.create(user=other,role='RA_QA')
        with self.assertRaises(PermissionDenied):svc.save_preview(other,token)
    def test_review_history_and_task_deduplication_preserve_operational_state(self):
        before=list(CustomerComplaint.objects.values('pk','status','version','due_date'));snap=self.snapshot()
        svc.comment(self.user,snap,'DEMO review one');svc.comment(self.user,snap,'DEMO correction, previous retained')
        task,created=self.task(snap);again,created2=self.task(snap);self.assertTrue(created);self.assertFalse(created2);self.assertEqual(task.pk,again.pk)
        self.assertEqual(snap.comments.count(),2);self.assertEqual(PMSPeriodAction.objects.count(),1)
        self.assertTrue(review_tasks.accessible(self.user,task.review_context))
        self.assertContains(self.client.get(reverse('market-task-list')),'DEMO investigation')
        self.assertContains(self.client.get(reverse('market-review-task-detail',args=[task.pk])),'PMS 분석 스냅샷')
        self.assertEqual(before,list(CustomerComplaint.objects.values('pk','status','version','due_date')))
        self.access.markets=['US'];self.access.save()
        self.assertFalse(review_tasks.accessible(self.user,task.review_context))
        self.assertEqual(self.client.get(reverse('market-review-task-api',args=[task.pk])).status_code,404)
    def test_malformed_api_inputs_return_validation_errors(self):
        snap=self.snapshot()
        for url in [reverse('market-pms-compare-api'),reverse('market-pms-task-api',args=[snap.pk,'CAPA']),reverse('market-pms-snapshot-api',args=[snap.pk])]:
            self.assertEqual(self.client.post(url,'{',content_type='application/json').status_code,400)
        self.assertEqual(self.client.post(reverse('market-pms-compare-api'),json.dumps({'action':'save','token':123}),content_type='application/json').status_code,400)
        self.assertEqual(self.client.post(reverse('market-pms-snapshot-api',args=[snap.pk]),json.dumps({'action':'comment','note':123}),content_type='application/json').status_code,400)
    def test_form_validation_and_real_api_compare_save_comment_task(self):
        params={k:(v.pk if k=='device' else v.isoformat() if isinstance(v,date) else v) for k,v in self.data().items()}
        response=self.client.get(reverse('market-pms-compare'),params);self.assertContains(response,'분석 결과 저장')
        payload=self.client.get(reverse('market-pms-compare-api'),params).json();self.assertEqual(self.metric(payload['result'])['b'],3)
        save=self.client.post(reverse('market-pms-compare-api'),{'action':'save','token':payload['token']});self.assertEqual(save.status_code,201);pk=save.json()['id']
        comment=self.client.post(reverse('market-pms-snapshot-api',args=[pk]),{'action':'comment','note':'DEMO investigation requested'});self.assertEqual(comment.status_code,200)
        task_data={'title':'DEMO HTTP task','assignee':self.user.pk,'criteria':'DEMO investigate','deadline_mode':'MANUAL','due_at':'2026-12-01T12:00:00+09:00','priority':'NORMAL'}
        url=reverse('market-pms-task-api',args=[pk,'INVESTIGATION']);task=self.client.post(url,task_data);self.assertEqual(task.status_code,201,task.content)
        self.assertEqual(self.client.post(url,task_data).json()['task_id'],task.json()['task_id'])
        self.assertEqual(self.client.get(reverse('market-pms-snapshots'),{'device':self.device.pk,'market':'DE','saved_from':timezone.localdate().isoformat()}).status_code,200)
        self.assertEqual(self.client.get(reverse('market-pms-compare-api'),{**params,'a_end':'2026-08-01'}).status_code,400)

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PeriodConcurrencyTests(Fixtures,TransactionTestCase):
    def setUp(self):self.setup_period()
    def test_concurrent_follow_up_requests_share_one_task(self):
        snap=self.snapshot();uid=self.user.pk;sid=snap.pk;barrier=Barrier(2)
        def run(_):
            close_old_connections()
            try:
                user=get_user_model().objects.get(pk=uid);snapshot=PMSPeriodSnapshot.objects.get(pk=sid)
                barrier.wait(timeout=10)
                task,created=svc.create_task(user,snapshot,'CAPA',assignee=user,title='DEMO concurrent task',criteria='DEMO inspect proof',due_at='2026-12-01T12:00:00+09:00')
                return task.pk,created
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(run,range(2)))
        self.assertEqual(len({pk for pk,_ in ids}),1);self.assertEqual(sum(created for _,created in ids),1);self.assertEqual(PMSPeriodAction.objects.count(),1)
