"""Synthetic fixtures only. Real model quality is measured separately, never by fake vectors."""
import hashlib,json,shutil
from datetime import date
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from .models import (Profile,RegulationDocument,RegulationChunk,Manufacturer,MedicalDevice,UDI,
    CustomerComplaint,ReportingRule,RuleApplication)
from .market_models import MarketAccess
from .fda_library import record_reference
from .eu_legal_models import EULegalDocument
from .eu_search_text import save_text,extract_articles
from .source_search import search,index_sources,candidates,rrf,split_text
from .regulation_documents import tokens
from .search_models import SourceSearchPassage,SourceSearchEmbedding,EULegalTextVersion
from .local_search_models import ModelUnavailable,identity

class FakeLocal:
    def encode(self,texts):return [[0.,1.] if 'serious incidents' in text or '사고' in text else [1.,0.] for text in texts]
    def rerank(self,query,texts):return list(range(len(texts)))

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SourceSearchTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('TEST-search-ra')
        Profile.objects.create(user=self.user,role='RA_QA')
        self.access=MarketAccess.objects.create(user=self.user,markets=['US','DE'])
        self.other=get_user_model().objects.create_user('TEST-search-us')
        Profile.objects.create(user=self.other,role='RA_QA');MarketAccess.objects.create(user=self.other,markets=['US'])
        self.source=self.fda()
        self.eu=EULegalDocument.objects.create(identifier='32017R0745',celex='32017R0745',official_url='https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32017R0745',title='TEST MDR fixture',source_type='eu_law',kind='eu_oj',language='en',checked_on=date(2026,11,17),recorded_by=self.user)
        self.raw=b'<p id="article87">Article 87</p><p>TEST serious incidents reporting; synthetic text only.</p><p>Article 88</p><p>TEST trend reporting.</p>'
        self.text,_=save_text(self.eu,self.raw,[87,88])
        with patch('pms.local_search_models.load',return_value=FakeLocal()):index_sources(self.user)
        SourceSearchEmbedding.objects.all().delete()
        self.client.force_login(self.user)
        self.url=reverse('market-source-search');self.api=reverse('market-source-search-api')
    def fda(self,version='TEST-v1',body='TEST MRI 510(k) premarket scope. Synthetic fixture only.'):
        return record_reference(dict(key='test-mrdd',title='TEST MRDD guidance',source_type='guidance',document_version=version,
            issued_on=None,revised_on=None,checked_on=date(2026,11,17),official_url='https://www.fda.gov/test-guidance',pdf_url='https://www.fda.gov/media/TEST/download',scope='TEST scope',device_types=['mri-equipment'],sections=[{'clause':'II. Scope','page':5}],pages={'5':body},metadata={},retrieval_status='verified_text',failure_reason=''))[0]
    def private_document(self):
        folder=Path.cwd()/'.test-media'/uuid4().hex;folder.mkdir(parents=True)
        self.addCleanup(shutil.rmtree,folder)
        self.enterContext(override_settings(MEDIA_ROOT=folder))
        body=b'TEST PRIVATE UNIQUE SECRET';(folder/'test.txt').write_bytes(body)
        doc=RegulationDocument.objects.create(title='TEST private',issuer='TEST',jurisdiction='US',scope_description='TEST',document_number='TEST-1',edition='TEST-private-v1',official_url='https://www.fda.gov/test',file='test.txt',original_name='test.txt',uploaded_by=self.user,visibility='PRIVATE',scan_status='PASSED',extraction_status='READY',sha256=hashlib.sha256(body).hexdigest(),is_example=True)
        RegulationChunk.objects.create(document=doc,sequence=1,paragraph=1,page=1,section='TEST section',text=body.decode(),content_hash=hashlib.sha256(body).hexdigest(),search_tokens=tokens(body.decode()))
        return doc,folder
    def test_incremental_duplicate_index(self):
        with patch('pms.local_search_models.load',return_value=FakeLocal()):
            first=index_sources(self.user);ids=list(SourceSearchPassage.objects.values_list('pk',flat=True))
            second=index_sources(self.user)
        self.assertGreater(first['embedded'],0);self.assertEqual(second['embedded'],0);self.assertEqual(second['created'],0)
        self.assertEqual(ids,list(SourceSearchPassage.objects.values_list('pk',flat=True)))
    def test_local_cross_language_fusion_and_no_external_call(self):
        with patch('pms.local_search_models.load',return_value=FakeLocal()),patch('urllib.request.urlopen',side_effect=AssertionError('external request')):
            index_sources(self.user)
            result=search(self.user,'중대한 사고 보고')
        self.assertEqual(result['engine'],'hybrid_rrf');self.assertEqual(result['results'][0]['jurisdiction'],'EU')
        self.assertFalse(result['external_inference'])
        self.assertEqual(rrf(['a','b'],['b','a'])[0],'a')
        self.assertEqual(rrf(['a'],['b','a'])[0],'a')
    def test_model_absent_and_missing_stale_corrupt_index(self):
        result=search(self.user,'510(k)');self.assertEqual(result['engine'],'keyword');self.assertEqual(result['fallback_reason'],'index_missing_or_stale')
        with patch('pms.local_search_models.load',return_value=FakeLocal()):index_sources(self.user)
        with patch('pms.local_search_models.load',side_effect=ModelUnavailable('model_not_cached')):
            result=search(self.user,'510(k)');self.assertEqual(result['fallback_reason'],'model_not_cached');self.assertTrue(result['results'])
        SourceSearchEmbedding.objects.update(vector=[0.])
        self.assertEqual(search(self.user,'510(k)')['fallback_reason'],'index_invalid')
    def test_versions_and_historical_text_preserved(self):
        before=self.text.text
        revised,_=save_text(self.eu,self.raw.replace(b'TEST trend',b'TEST revised trend'),[87,88])
        self.assertEqual(revised.version,2);self.text.refresh_from_db();self.assertEqual(self.text.text,before)
        repeated,created=save_text(self.eu,self.raw,[87,88]);self.assertFalse(created);self.assertEqual(repeated.pk,self.text.pk)
        v2=self.fda('TEST-v2','TEST revised MRI 510(k) scope.')
        self.assertNotEqual(v2.pk,self.source.pk)
        result=search(self.user,'510(k)',mode='keyword',edition='TEST-v1')
        self.assertTrue(result['results']);self.assertEqual({r['version'] for r in result['results']},{'TEST-v1'})
    def test_permissions_private_revocation_and_original_links(self):
        doc,folder=self.private_document()
        def contains_private(result):return any(row['kind']=='regulation' and row['document_id']==doc.pk for row in result['results'])
        self.assertTrue(contains_private(search(self.user,'PRIVATE UNIQUE',mode='keyword')))
        self.assertFalse(contains_private(search(self.other,'PRIVATE UNIQUE',mode='keyword')))
        self.assertFalse(search(self.other,'serious incidents',mode='keyword',jurisdiction='EU')['results'])
        result=search(self.user,'serious incidents',mode='keyword',jurisdiction='EU')
        self.assertIn('#article87',result['results'][0]['official_url'])
        (folder/'test.txt').write_text('TAMPER',encoding='utf-8')
        self.assertFalse(contains_private(search(self.user,'PRIVATE UNIQUE',mode='keyword')))
        self.access.markets=[];self.access.save()
        self.assertEqual(self.client.get(self.api,{'query':'510(k)','mode':'keyword'}).json()['results'],[])
    def test_ui_api_defaults_roles_and_version_filter(self):
        self.assertEqual(self.client.get(self.url).status_code,200)
        empty=self.client.get(self.api)
        self.assertEqual(empty.status_code,400);self.assertIn('query',empty.json()['errors'])
        response=self.client.get(self.url,{'query':'510(k)','mode':'ai'})
        self.assertContains(response,'실제 검색 방식: keyword');self.assertContains(response,'대체 실행')
        self.assertContains(response,'미확인');self.assertContains(response,'공식 원문 열기')
        response=self.client.get(self.api,{'query':'510(k)','edition':'TEST-v1','mode':'keyword'})
        self.assertEqual(response.status_code,200);self.assertLessEqual(len(response.json()['results']),5)
        staff=get_user_model().objects.create_user('TEST-staff');Profile.objects.create(user=staff,role='STAFF');self.client.force_login(staff)
        self.assertEqual(self.client.get(self.api,{'query':'510(k)'}).status_code,403)
    def test_scoped_source_location_and_download_recheck_access(self):
        doc,folder=self.private_document()
        result=search(self.user,'PRIVATE UNIQUE',mode='keyword')
        row=next(row for row in result['results'] if row['kind']=='regulation' and row['document_id']==doc.pk)
        response=self.client.get(row['location_url'])
        self.assertEqual(response.status_code,200);self.assertNotContains(response,'cdn.jsdelivr.net')
        original=reverse('market-source-original',args=[doc.pk])
        response=self.client.get(original);self.assertEqual(response.status_code,200)
        self.assertEqual(b''.join(response.streaming_content),b'TEST PRIVATE UNIQUE SECRET')
        self.client.force_login(self.other);self.assertEqual(self.client.get(original).status_code,404)
        self.client.force_login(self.user);self.access.markets=[];self.access.save()
        self.assertEqual(self.client.get(row['location_url']).status_code,404)
        self.assertEqual(self.client.get(original).status_code,404)
    def test_optional_reranker_fallback(self):
        with patch('pms.local_search_models.load',return_value=FakeLocal()):index_sources(self.user)
        with override_settings(SOURCE_SEARCH_RERANKER_ENABLED=True),patch('pms.local_search_models.load',side_effect=lambda reranker=False: FakeLocal()):
            self.assertEqual(search(self.user,'510(k)')['engine'],'hybrid_rrf_reranked')
        def unavailable(reranker=False):
            if reranker:raise ModelUnavailable('model_not_cached')
            return FakeLocal()
        with override_settings(SOURCE_SEARCH_RERANKER_ENABLED=True),patch('pms.local_search_models.load',side_effect=unavailable):
            result=search(self.user,'510(k)');self.assertEqual(result['engine'],'hybrid_rrf');self.assertEqual(result['reranker_reason'],'reranker_unavailable')
    def test_search_does_not_apply_rules_or_change_case_snapshots(self):
        maker=Manufacturer.objects.create(name='TEST');device=MedicalDevice.objects.create(name='TEST',manufacturer=maker,model_number='TEST')
        udi=UDI.objects.create(device=device,device_identifier='TEST')
        case=CustomerComplaint.objects.create(device=device,udi=udi,reporter=self.user,complaint_type='TEST',title='TEST',description='TEST',occurred_on=date(2026,1,1),due_date=date(2026,1,10))
        rule=ReportingRule.objects.create(name='TEST',state='DRAFT',change_reason='TEST')
        snapshot=RuleApplication.objects.create(complaint=case,rule=rule,snapshot={'TEST':'immutable'},due_at=timezone.now(),actor=self.user,reason='TEST')
        before=(case.status,case.due_date,rule.state,snapshot.snapshot.copy())
        with patch('pms.local_search_models.load',return_value=FakeLocal()):
            index_sources(self.user);search(self.user,'사고');search(self.user,'510(k)',mode='keyword')
        case.refresh_from_db();rule.refresh_from_db();snapshot.refresh_from_db()
        self.assertEqual(before,(case.status,case.due_date,rule.state,snapshot.snapshot))
    def test_eu_fetch_failure_is_not_empty_success(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from types import SimpleNamespace
        response=SimpleNamespace(status=202,headers={},geturl=lambda:self.eu.official_url,read=lambda n:b'')
        with patch('pms.eu_acquisition.time.sleep'),patch('pms.eu_acquisition.open_official') as remote:
            remote.return_value.__enter__.return_value=response
            with self.assertRaises(CommandError):call_command('fetch_eu_search_text',user=self.user.username,document=self.eu.pk,articles='87')
        self.assertEqual(EULegalTextVersion.objects.count(),1)
        with self.assertRaises(ValueError):extract_articles(b'<script>instructions</script>',[87])
    def test_pinned_revision_validation(self):
        with override_settings(SOURCE_SEARCH_REVISION='main'):
            with self.assertRaises(ModelUnavailable):identity()
    def test_section_boundaries_and_incremental_new_version(self):
        parts=list(split_text('I. Introduction\nTEST introduction paragraph is synthetic.\nII. Scope\nTEST scope paragraph is synthetic.'))
        self.assertEqual([section for section,_ in parts],['I. Introduction','II. Scope'])
        self.assertNotIn('II. Scope',parts[0][1])
        with patch('pms.local_search_models.load',return_value=FakeLocal()):
            index_sources(self.user)
            before=list(SourceSearchEmbedding.objects.order_by('pk').values('pk','passage_id','vector','indexed_at'))
            self.fda('TEST-v3','TEST revised scope; MRI 510(k) synthetic fixture.')
            result=index_sources(self.user)
        self.assertEqual(result['embedded'],1)
        self.assertEqual(list(SourceSearchEmbedding.objects.filter(pk__in=[row['pk'] for row in before]).order_by('pk').values('pk','passage_id','vector','indexed_at')),before)
