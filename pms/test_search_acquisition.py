"""Synthetic regression fixtures; live official/model measurements are separate outputs."""
from pathlib import Path
from uuid import uuid4
import shutil
from unittest.mock import patch
from types import SimpleNamespace
from django.test import TestCase,override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from . import test_source_search as fixtures
FakeLocal=fixtures.FakeLocal
from .search_models import EUSearchHead,EULegalTextVersion,EUSourceAttempt,SourceSearchEmbedding,SourceSearchExecution,SearchEvidenceAdoption
from .source_search import candidates,index_sources,search
from .eu_search_text import save_text
from .eu_acquisition import acquire,parse_official,AcquisitionError,retry_delay,discover_op_download
from .search_history import record_execution,adopt,adoption_access
from .local_search_models import token_windows,ModelUnavailable

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AcquisitionTests(TestCase):
    setUp=fixtures.SourceSearchTests.setUp
    fda=fixtures.SourceSearchTests.fda
    def test_pending_is_hidden_and_success_publishes_atomically(self):
        old=EUSearchHead.objects.get(document=self.eu).active_text_id
        revised,_=save_text(self.eu,self.raw.replace(b'TEST trend',b'TEST revised trend'),[87,88])
        self.assertEqual({r['source_id'] for r in candidates(self.user,jurisdiction='EU')},{old})
        with patch('pms.local_search_models.load',side_effect=ModelUnavailable('model_not_cached')):
            with self.assertRaises(ModelUnavailable):index_sources(self.user)
        self.assertEqual(EUSearchHead.objects.get(document=self.eu).active_text_id,old)
        with patch('pms.local_search_models.load',return_value=FakeLocal()):
            index_sources(self.user);again=index_sources(self.user)
        self.assertEqual(EUSearchHead.objects.get(document=self.eu).active_text_id,revised.pk)
        self.assertEqual(again['created'],0);self.assertEqual(again['embedded'],0)
    def test_retry_statuses_keep_last_good_head(self):
        old=EUSearchHead.objects.get(document=self.eu).active_text_id
        response=SimpleNamespace(status=202,headers={'Retry-After':'0'},geturl=lambda:self.eu.official_url,read=lambda n:b'')
        with patch('pms.eu_acquisition.open_official') as remote,patch('pms.eu_acquisition.time.sleep') as sleep:
            remote.return_value.__enter__.return_value=response
            with self.assertRaises(AcquisitionError):acquire(self.eu,self.user,[87],max_attempts=2)
        self.assertEqual(remote.call_count,6);self.assertEqual(sleep.call_count,3)
        self.assertEqual(set(EUSourceAttempt.objects.values_list('status',flat=True)),{'HTTP_202'})
        self.assertEqual(EUSearchHead.objects.get(document=self.eu).active_text_id,old)
    def test_empty_blocked_invalid_pdf_distinct(self):
        for raw,status in [(b'', 'EMPTY_BODY'),(b'<html>Access denied</html>','BLOCKED_PAGE'),(b'%PDF-broken','PDF_EXTRACTION_FAILED')]:
            with self.subTest(status=status),self.assertRaises(AcquisitionError) as error:parse_official(self.eu,raw,[87])
            self.assertEqual(error.exception.status,status)
    def test_manual_import_validates_identity_and_deduplicates(self):
        raw=b'<html lang="en"><title>Document 32017R0745</title><p>Article 87</p><p>TEST serious incidents are reported with traceable evidence.</p><p>Article 88</p></html>'
        folder=Path.cwd()/'.test-media'/uuid4().hex;folder.mkdir(parents=True)
        self.addCleanup(shutil.rmtree,folder)
        with override_settings(MEDIA_ROOT=folder):
            file=Path(folder)/'official.html';file.write_bytes(raw)
            first,created=acquire(self.eu,self.user,[87],input_file=file)
            second,created2=acquire(self.eu,self.user,[87],input_file=file)
            self.assertTrue(created);self.assertFalse(created2);self.assertEqual(first.pk,second.pk)
            self.assertTrue(first.verification['identity_verified'])
            file.write_bytes(raw.replace(b'32017R0745',b'32017R0746'))
            with self.assertRaises(AcquisitionError) as error:acquire(self.eu,self.user,[87],input_file=file)
            self.assertEqual(error.exception.status,'IDENTITY_MISMATCH')
    def test_manual_screen_permission_and_metadata_validation(self):
        url=reverse('market-search-eu-manage',args=[self.eu.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,{'celex':'wrong','language':'en','version':'wrong','articles':'87','confirm':'on','action':'fetch'}).status_code,400)
        self.client.force_login(self.other);self.assertEqual(self.client.get(url).status_code,404)
    def test_language_and_version_filters_before_models(self):
        self.assertFalse(candidates(self.user,language='de'))
        self.assertTrue(candidates(self.user,language='en',jurisdiction='EU'))
        self.assertFalse(candidates(self.user,jurisdiction='EU',edition='nonexistent'))
    def test_retry_after_and_official_alternative_identity(self):
        self.assertEqual(retry_delay('7',1),7)
        self.assertEqual(retry_delay(None,3),4)
        with self.assertRaises(AcquisitionError):discover_op_download(b'<html>other CELEX</html>',self.eu)
    def test_token_windows_retain_entire_long_source(self):
        values=list(range(1300));windows=token_windows(values,128)
        self.assertEqual(set(v for window in windows for v in window),set(values))
        self.assertTrue(all(len(w)<=128 for w in windows))
    def test_history_malformed_filter_rejected(self):
        self.assertEqual(self.client.get(reverse('market-search-history'),{'draft':'bad'}).status_code,404)
    def test_search_execution_is_owner_scoped_and_snapshotted(self):
        result=search(self.user,'510(k)',mode='keyword')
        event=record_execution(self.user,'510(k)',{},result)
        before=event.snapshot.copy();self.fda('TEST-v2','TEST changed source content.')
        event.refresh_from_db();self.assertEqual(event.snapshot,before)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('market-search-execution',args=[event.pk])).status_code,404)
    def test_evidence_adoption_preserves_existing_draft_and_revocation(self):
        from .models import Manufacturer,MedicalDevice
        from .dental_models import DentalGuide,DentalProject,DentalDraft
        guide=DentalGuide.objects.create(issued_on='2026-11-18',status='TEST',url='https://www.fda.gov/test',checked_on='2026-11-18',sha256='a'*64,sections=[])
        device=MedicalDevice.objects.create(name='TEST',model_number='TEST',manufacturer=Manufacturer.objects.create(name='TEST'))
        from .market_models import ProductMarket
        ProductMarket.objects.create(device=device,market='US')
        project=DentalProject.objects.create(device=device,guide=guide,specification={},market='US')
        draft=DentalDraft.objects.create(project=project,author=self.user,snapshot={'rows':[],'unchanged':'TEST'})
        result=search(self.user,'510(k)',mode='keyword');event=record_execution(self.user,'510(k)',{},result)
        item,created=adopt(self.user,event,result['results'][0]['key'],draft=draft,rationale='TEST rationale')
        duplicate,created2=adopt(self.user,event,result['results'][0]['key'],draft=draft,rationale='TEST rationale')
        self.assertEqual(item.pk,duplicate.pk);self.assertFalse(created2)
        before=item.snapshot.copy();self.fda('TEST-v3','TEST updated source.')
        item.refresh_from_db();draft.refresh_from_db()
        self.assertEqual(item.snapshot,before);self.assertEqual(draft.snapshot,{'rows':[],'unchanged':'TEST'})
        self.assertEqual(self.client.get(reverse('market-search-adoption',args=[item.pk])).status_code,200)
        self.access.markets=[];self.access.save();self.assertFalse(adoption_access(self.user,item))
        self.assertEqual(self.client.get(reverse('market-search-adoption',args=[item.pk])).status_code,404)

    def test_interrupted_build_and_late_old_build_never_publish(self):
        from .source_search import sync_passages,publish_eu
        from .local_search_models import identity,profile
        old=EUSearchHead.objects.get(document=self.eu).active_text_id
        staged,_=save_text(self.eu,self.raw.replace(b'TEST trend',b'TEST amended trend'),[87,88])
        rows=candidates(self.user,jurisdiction='EU',include_pending=True)
        sync_passages(rows)
        with self.assertRaises(ValidationError):publish_eu(rows,*identity(),profile())
        self.assertEqual(EUSearchHead.objects.get(document=self.eu).active_text_id,old)
        newest,_=save_text(self.eu,self.raw.replace(b'TEST trend',b'TEST newest trend'),[87,88])
        self.assertEqual(publish_eu(rows,*identity(),profile()),0)
        self.assertEqual(EUSearchHead.objects.get(document=self.eu).active_text_id,old)
        with patch('pms.local_search_models.load',return_value=FakeLocal()):index_sources(self.user)
        self.assertEqual(EUSearchHead.objects.get(document=self.eu).active_text_id,newest.pk)
