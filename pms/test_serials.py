import json
from datetime import date
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import IntegrityError,connection,close_old_connections,transaction
from django.test import TestCase,TransactionTestCase
from django.urls import reverse
from .models import Manufacturer,MedicalDevice,Profile,UDI,ProductLot,TaskHistory,AuditLog
from .market_models import ProductMarket,MarketAccess
from .serial_models import ManufacturingSerial,SerialDispatchRecord,UDILabelIncident,UDILabelFollowup
from .serial_service import issue_serial,import_lot,MAX_SERIAL_ATTEMPTS
from .gs1 import valid_gtin14,human_udi,compare_label

GTIN='09506000134352' # Explicit test fixture only; never a production default.
DAY=date(2026,11,13)

def setup_records(obj):
    obj.user=get_user_model().objects.create_user('serial-ra')
    Profile.objects.create(user=obj.user,role='RA_QA')
    obj.access=MarketAccess.objects.create(user=obj.user,markets=['US'])
    manufacturer=Manufacturer.objects.create(name='DEMO Manufacturer')
    obj.device=MedicalDevice.objects.create(name='DEMO MRI',model_number='DEMO-SERIAL-A',manufacturer=manufacturer,product_type='MRI',gtin_14=GTIN)
    ProductMarket.objects.create(device=obj.device,market='US',is_example=True)

class SerialTests(TestCase):
    def setUp(self):
        setup_records(self);self.client.force_login(self.user)
        self.url=reverse('market-serials',args=[self.device.pk])
        self.api=reverse('market-serial-api',args=[self.device.pk])
    def issue(self,key=None,**changes):
        return issue_serial(self.user,self.device,**{'gtin_snapshot':GTIN,'manufactured_on':DAY,'request_key':key or uuid4(),**changes})
    def test_gtin_and_date(self):
        self.assertTrue(valid_gtin14(GTIN));self.assertFalse(valid_gtin14(GTIN[:-1]+'3'))
        self.assertFalse(valid_gtin14('９'*14));self.assertFalse(valid_gtin14('9506000134352'))
        for gtin,day in [(GTIN[:-1]+'3','2026-11-13'),(GTIN,'2026-02-30')]:
            response=self.client.post(self.api,json.dumps(dict(gtin_snapshot=gtin,manufactured_on=day,request_key=str(uuid4()))),content_type='application/json')
            self.assertEqual(response.status_code,400)
        self.assertEqual(ManufacturingSerial.objects.count(),0)
        self.assertEqual(self.client.post(self.api,json.dumps(dict(gtin_snapshot=GTIN,manufactured_on=123,request_key=str(uuid4()))),content_type='application/json').status_code,400)
    def test_format_ai_data_and_scanner(self):
        expected=human_udi(GTIN,DAY,'M7Q2K9R4T6')
        self.assertEqual(expected,'(01)09506000134352(11)261113(21)M7Q2K9R4T6')
        result=compare_label(expected.replace('(11)','(17)'),GTIN,DAY,'M7Q2K9R4T6')
        self.assertEqual(result['ai_errors'][0]['field'],'11');self.assertEqual(result['value_errors'],[])
        result=compare_label(expected.replace('261113','261114'),GTIN,DAY,'M7Q2K9R4T6')
        self.assertEqual(result['ai_errors'],[]);self.assertEqual(result['value_errors'][0]['field'],'11')
        self.assertTrue(compare_label(']d201'+GTIN+'1126111321M7Q2K9R4T6',GTIN,DAY,'M7Q2K9R4T6')['valid'])
        self.assertFalse(compare_label(expected+'(10)extra',GTIN,DAY,'M7Q2K9R4T6')['valid'])
    def test_issue_idempotence_and_frozen_gtin(self):
        key=uuid4();record,created=self.issue(key);self.assertTrue(created)
        self.assertRegex(record.serial_number,r'^[A-Z0-9]{10}$')
        self.assertEqual(self.issue(key)[0].pk,record.pk);self.assertFalse(self.issue(key)[1])
        with self.assertRaises(ValidationError):self.issue(key,manufactured_on=date(2026,11,14))
        before=record.expected_udi
        self.device.gtin_14='00000000000000';self.device.save()
        self.assertEqual(self.issue(key)[0].expected_udi,before)
        with self.assertRaises(ValidationError):self.issue()
        self.assertEqual(ManufacturingSerial.objects.count(),1)
    def test_snapshot_and_ui(self):
        self.assertContains(self.client.get(self.url),'제조번호 발급')
        record,_=self.issue();url=reverse('market-serial',args=[self.device.pk,record.pk])
        response=self.client.get(url);self.assertContains(response,record.expected_udi);self.assertContains(response,'UDI 복사')
        response=self.client.post(url,{'action':'validate','printed_udi':record.expected_udi.replace('(11)','(17)')})
        self.assertContains(response,'AI 오류');self.assertContains(response,'AI 뒤 데이터 값 불일치')
    def test_collision_retry_only_named_constraint(self):
        first,_=self.issue()
        with patch('pms.serial_service.generate_serial',side_effect=[first.serial_number,'A123456789']):
            second,_=self.issue();self.assertEqual(second.serial_number,'A123456789')
        with patch('pms.serial_service.generate_serial',return_value=first.serial_number) as generate:
            with self.assertRaises(ValidationError):self.issue()
            self.assertEqual(generate.call_count,MAX_SERIAL_ATTEMPTS)
        with patch.object(ManufacturingSerial.objects,'create',side_effect=IntegrityError('unrelated foreign key')) as create:
            with self.assertRaises(IntegrityError):self.issue()
            self.assertEqual(create.call_count,1)
    def test_legacy_duplicates_and_cloned_product(self):
        udi=UDI.objects.create(device=self.device,device_identifier=GTIN)
        # Historical duplicates existed before the new write service: preserve both originals.
        ProductLot.objects.bulk_create([ProductLot(device=self.device,udi=udi,lot_number=f'OLD-{i}',serial_number='A123456789',manufactured_on=DAY,distributed_quantity=i) for i in (1,2)])
        original=list(ProductLot.objects.values('pk','serial_number','distributed_quantity','manufactured_on'))
        clone=MedicalDevice.objects.create(name='DEMO clone',manufacturer=self.device.manufacturer,model_number='DEMO-CLONE',gtin_14=GTIN)
        ProductMarket.objects.create(device=clone,market='US')
        with patch('pms.serial_service.generate_serial',side_effect=['A123456789','B123456789']):
            record,_=issue_serial(self.user,clone,GTIN,DAY,uuid4())
        self.assertEqual(record.serial_number,'B123456789')
        imported=ManufacturingSerial.objects.get(serial_number='A123456789')
        self.assertEqual(imported.lot_references.count(),2);self.assertEqual(imported.expected_udi,'')
        self.assertIn('중복',imported.status)
        self.assertEqual(list(ProductLot.objects.values('pk','serial_number','distributed_quantity','manufactured_on')),original)
        from django.core.management import call_command
        from io import StringIO
        out=StringIO();call_command('report_serial_duplicates',stdout=out)
        self.assertEqual(len(json.loads(out.getvalue())['duplicates'][0]['lot_ids']),2)
    def test_manual_lot_registration_and_regression(self):
        udi=UDI.objects.create(device=self.device,device_identifier=GTIN)
        record,_=self.issue()
        lot=ProductLot.objects.create(device=self.device,udi=udi,lot_number='DEMO-LOT',serial_number=record.serial_number,manufactured_on=DAY)
        self.assertEqual(lot.serial_identity_id,record.pk)
        lot.distributed_quantity=1;lot.save();self.assertEqual(record.lot_references.count(),1)
        with self.assertRaises(ValidationError):ProductLot.objects.create(device=self.device,udi=udi,lot_number='DIFFERENT',serial_number=record.serial_number)
        self.assertEqual(self.client.get(reverse('market-device-detail',args=[self.device.pk])).status_code,200)
        self.device.gtin_14='';self.device.save(update_fields=['gtin_14'])
        raw_udi=UDI.objects.create(device=self.device,device_identifier='DEMO-UNRESOLVED')
        old=ProductLot.objects.create(device=self.device,udi=raw_udi,lot_number='OLD',serial_number='OLD1234567',manufactured_on=DAY)
        unresolved=import_lot(old);self.assertEqual(unresolved.gtin_14,'')
        self.assertEqual(self.client.post(self.url,{'action':'gtin','gtin_14':GTIN}).status_code,302)
        self.assertTrue(ManufacturingSerial.objects.get(gtin_14=GTIN,serial_number=old.serial_number).expected_udi)
        unresolved.refresh_from_db();self.assertEqual(unresolved.gtin_14,'')
        old.refresh_from_db();self.assertEqual((old.serial_number,old.manufactured_on),('OLD1234567',DAY))
    def test_permissions_replay_and_revocation(self):
        record,_=self.issue();self.access.markets=['DE'];self.access.save()
        for url in (self.url,reverse('market-serial',args=[self.device.pk,record.pk])):
            self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.post(self.api,json.dumps(dict(gtin_snapshot=GTIN,manufactured_on=str(DAY),request_key=str(record.request_key))),content_type='application/json').status_code,404)
        other=get_user_model().objects.create_user('staff');Profile.objects.create(user=other,role='STAFF');self.client.force_login(other)
        self.assertEqual(self.client.post(self.api,'{}',content_type='application/json').status_code,403)
    def test_shipped_label_pms_and_append_only_correction(self):
        self.client.post(self.url,{'action':'profile','market':'US'})
        profile=self.device.regulatory_profiles.get()
        record,_=self.issue();url=reverse('market-serial',args=[self.device.pk,record.pk])
        printed=record.expected_udi.replace('(11)','(17)')
        self.assertEqual(self.client.post(url,{'action':'dispatch','dispatched_on':'2026-11-14','reference':'DEMO-DISPATCH','printed_udi':printed}).status_code,302)
        dispatch=record.dispatches.get();original=dispatch.printed_udi
        response=self.client.post(url,{'action':'incident','profile':profile.pk,'printed_udi':printed,'dispatches':[dispatch.pk],'due_at':'2026-11-20T16:00'})
        self.assertEqual(response.status_code,302,response.content[:300])
        incident=UDILabelIncident.objects.get();self.assertEqual(incident.differences['printed']['value_errors'],[])
        self.assertTrue(incident.differences['printed']['ai_errors'])
        self.assertEqual(incident.dispatch_links.get().original['printed_udi'],original)
        target=reverse('market-udi-incident',args=[self.device.pk,incident.pk])
        self.assertEqual(self.client.post(target,{'action_type':'CORRECTION','rationale':'DEMO AI만 정정 검토','corrected_udi':record.expected_udi,'status':'REVIEW','previous':0}).status_code,302)
        self.assertEqual(self.client.post(target,{'action_type':'NOTICE','rationale':'outdated form','status':'DONE','previous':0}).status_code,409)
        self.assertEqual(UDILabelFollowup.objects.count(),1)
        dispatch.refresh_from_db();incident.refresh_from_db();self.assertEqual(dispatch.printed_udi,original);self.assertEqual(incident.printed_udi,printed)
        self.assertEqual(TaskHistory.objects.filter(task=incident.task).count(),2)
        from .workflow import tasks_for
        self.assertTrue(tasks_for(self.user).filter(pk=incident.task_id).exists())
        self.access.markets=['DE'];self.access.save();self.assertEqual(self.client.get(target).status_code,404)
        self.user.refresh_from_db() # clear the cached market grant for a fresh service request
        self.assertFalse(tasks_for(self.user).filter(pk=incident.task_id).exists())

    def test_database_uniqueness_across_clones(self):
        record,_=self.issue()
        clone=MedicalDevice.objects.create(name='DEMO clone',manufacturer=self.device.manufacturer,model_number='DEMO-DB-CLONE',gtin_14=GTIN)
        with self.assertRaises(IntegrityError),transaction.atomic():
            ManufacturingSerial.objects.create(device=clone,gtin_14=GTIN,serial_number=record.serial_number,origin='MANUAL')
        # The namespace is GTIN, not the product record or serial alone.
        other=ManufacturingSerial.objects.create(device=clone,gtin_14='00000000000000',serial_number=record.serial_number,origin='MANUAL')
        self.assertNotEqual(other.pk,record.pk)

    def test_evidence_scope_integrity_and_download(self):
        from pathlib import Path
        import hashlib,shutil
        from django.test import override_settings
        from .models import Attachment
        folder=Path.cwd()/f'serial_test_{uuid4().hex}';folder.mkdir()
        self.addCleanup(shutil.rmtree,folder)
        self.enterContext(override_settings(MEDIA_ROOT=folder))
        raw=b'DEMO label evidence only';(folder/'proof.txt').write_bytes(raw)
        self.client.post(self.url,{'action':'profile','market':'US'});profile=self.device.regulatory_profiles.get()
        attachment=Attachment.objects.create(ra_profile=profile,uploaded_by=self.user,file='proof.txt',original_name='DEMO-proof.txt',scan_status='PASSED',sha256=hashlib.sha256(raw).hexdigest())
        record,_=self.issue();url=reverse('market-serial',args=[self.device.pk,record.pk])
        data={'action':'incident','profile':profile.pk,'printed_udi':record.expected_udi.replace('(11)','(17)'),'evidence':[attachment.pk],'due_at':'2026-11-20T16:00'}
        self.assertEqual(self.client.post(url,data).status_code,302)
        incident=UDILabelIncident.objects.get()
        download=reverse('market-udi-evidence',args=[self.device.pk,incident.pk,attachment.pk])
        response=self.client.get(download);self.assertEqual(response.status_code,200);self.assertEqual(b''.join(response.streaming_content),raw)
        clone=MedicalDevice.objects.create(name='DEMO other',manufacturer=self.device.manufacturer,model_number='DEMO-OTHER',gtin_14=GTIN)
        ProductMarket.objects.create(device=clone,market='US')
        # Even another accessible product cannot supply evidence to this incident.
        from .ra_services import save_record
        from .models import RegulatoryProfile
        other_profile=save_record(RegulatoryProfile(),self.user,dict(device=clone,jurisdiction='US',organization=profile.organization,organization_role='MANUFACTURER',title='DEMO other',owner=self.user),'DEMO')
        other=Attachment.objects.create(ra_profile=other_profile,uploaded_by=self.user,file='proof.txt',scan_status='PASSED',sha256=attachment.sha256)
        self.assertEqual(self.client.post(url,{**data,'evidence':[other.pk]}).status_code,400)
        attachment.sha256='0'*64;attachment.save(update_fields=['sha256'])
        self.assertEqual(self.client.get(download).status_code,404)
        self.access.markets=[];self.access.save();self.assertEqual(self.client.get(download).status_code,404)

class SerialConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor=='sqlite' and ('memory' in str(connection.settings_dict['NAME'])):self.skipTest('File-backed SQLite required: set SQLITE_TEST_PATH; run separately.')
        setup_records(self)
    def run_parallel(self,same_key):
        barrier=Barrier(2);key=uuid4();user_id=self.user.pk;device_id=self.device.pk
        def run(i):
            close_old_connections()
            try:
                user=get_user_model().objects.get(pk=user_id);device=MedicalDevice.objects.get(pk=device_id)
                barrier.wait(timeout=10)
                record,created=issue_serial(user,device,GTIN,DAY,key if same_key else uuid4())
                return record.pk,record.serial_number,created
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,(0,1)))
        return results
    def test_concurrent_distinct_requests(self):
        results=self.run_parallel(False);self.assertNotEqual(results[0][1],results[1][1]);self.assertEqual(ManufacturingSerial.objects.count(),2)
    def test_concurrent_same_request(self):
        results=self.run_parallel(True);self.assertEqual(results[0][:2],results[1][:2]);self.assertEqual(sum(row[2] for row in results),1)
        self.assertEqual(ManufacturingSerial.objects.count(),1)
