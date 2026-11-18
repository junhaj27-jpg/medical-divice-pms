import io,json
from copy import deepcopy
from zipfile import ZipFile
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError,PermissionDenied
from . import test_source_search as fixtures
from .models import Manufacturer,MedicalDevice
from .market_models import ProductMarket
from .dental_models import WritingTemplate,DentalGuide,DentalProject
from .dossier_models import RADocument,RADocumentRevision,RADocumentReview
from . import dossier as svc
from .search_history import record_execution,adopt
from .source_search import search

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DossierTests(TestCase):
    fda=fixtures.SourceSearchTests.fda
    def setUp(self):
        fixtures.SourceSearchTests.setUp(self)
        self.device=MedicalDevice.objects.create(name='DEMO MRI',model_number='DEMO-MRI-1',manufacturer=Manufacturer.objects.create(name='DEMO'))
        ProductMarket.objects.create(device=self.device,market='US',is_example=True)
        self.template=WritingTemplate.objects.create(key='test-dossier',name='TEST Description',state='DRAFT',market='US',checked_on='2026-11-18',conditions={'internal_collection':True},items=[{'id':'DESC','title':'Device Description','page':1,'mapping':'Internal review','condition':'always','source_section':'II. Scope','evidence_type':'Specification','draft_section':'Device Description'}])
        self.template.state='REVIEW';self.template.save()
        self.template.state='PUBLISHED';self.template.save()
        guide=DentalGuide.objects.create(issued_on='2026-11-18',status='TEST',url='https://www.fda.gov/test',checked_on='2026-11-18',sha256='a'*64,sections={})
        self.project=DentalProject.objects.create(device=self.device,template=self.template,guide=guide,specification={'product_name':'DEMO MRI','model':'DEMO-MRI-1','intended_use':'DEMO internal test use','example':True,'changed':False})
        self.revision=svc.create_document(self.user,self.project,'description','US','en','TEST initial')
        self.url=reverse('market-ra-document-api',args=[self.revision.pk])
    def link(self):
        result=search(self.user,'510(k)',mode='keyword',jurisdiction='US',edition='TEST-v1')
        event=record_execution(self.user,'510(k)',{},result)
        adoption,_=adopt(self.user,event,result['results'][0]['key'],draft=self.revision.draft,rationale='TEST basis')
        data={'refs_DESC':[adoption.pk]}
        snapshot=svc.edited_snapshot(self.user,self.revision,data)
        return svc.save_revision(self.user,self.revision.document,snapshot,'TEST source link',self.revision.number)
    def test_full_review_flow_and_frozen_exports(self):
        revision=self.link();original=deepcopy(revision.draft.snapshot)
        validation=svc.validate(self.user,revision)
        self.assertFalse(any(f['severity']=='ERROR' for f in validation.findings))
        event=svc.review(self.user,revision,'REQUESTED','TEST request',0)
        approved=svc.review(self.user,revision,'APPROVED','TEST suitability checked',event.pk,True)
        self.assertEqual(svc.version_state(revision),'APPROVED')
        self.assertEqual(revision.draft.reviews.count(),1)
        xml=ZipFile(io.BytesIO(svc.export_docx(self.user,revision))).read('word/document.xml').decode()
        self.assertIn('APPROVED',xml);self.assertIn('TEST-v1',xml);self.assertIn('Draft for RA Review',xml)
        changed=deepcopy(original);changed['rows'][0]['body']+=' TEST correction'
        next_version=svc.save_revision(self.user,revision.document,changed,'TEST corrected',revision.number)
        self.assertEqual(svc.version_state(next_version),'REVIEW_REQUIRED')
        revision.draft.refresh_from_db();self.assertEqual(revision.draft.snapshot,original)
        self.assertEqual(revision.review_events.count(),2)
    def test_missing_info_model_mismatch_and_invalid_clause(self):
        revision=self.link();snapshot=deepcopy(revision.draft.snapshot)
        snapshot['specification']['intended_use']='';snapshot['rows'][0]['product_model']='WRONG'
        snapshot['rows'][0]['search_references'][0]['section']='NONEXISTENT ARTICLE'
        bad=svc.save_revision(self.user,revision.document,snapshot,'TEST invalid inputs',revision.number)
        result=svc.validate(self.user,bad);codes={r['code'] for r in result.findings}
        self.assertTrue({'MISSING_PRODUCT','MODEL_MISMATCH','INVALID_CITATION'}<=codes)
        event=svc.review(self.user,bad,'REQUESTED','TEST request',0)
        with self.assertRaises(ValidationError):svc.review(self.user,bad,'APPROVED','TEST',event.pk,True)
    def test_source_amendment_impacts_and_prior_snapshot_preserved(self):
        revision=self.link();before=deepcopy(revision.draft.snapshot)
        self.fda('TEST-v2','TEST revised MRI 510(k) premarket scope.')
        changed=svc.impacts(self.user,revision)
        self.assertTrue(changed);self.assertEqual(changed[0]['state'],'REVIEW_REQUIRED')
        response=self.client.get(reverse('market-ra-impacts-api'));self.assertEqual(response.status_code,200)
        item=next(i for i in response.json()['items'] if i['id']==revision.pk)
        response=self.client.post(reverse('market-ra-impacts-api'),json.dumps({**item,'state':'IN_PROGRESS','reason':'TEST change','expected':0}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        revision.draft.refresh_from_db();self.assertEqual(revision.draft.snapshot,before)
    def test_document_and_source_permissions_rechecked_in_api_and_exports(self):
        revision=self.link();url=reverse('market-ra-document-api',args=[revision.pk])
        self.access.markets=[];self.access.save()
        for path in [url,reverse('market-ra-document',args=[revision.pk]),reverse('market-ra-document-output',args=[revision.pk,'docx'])]:self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.post(url,{'action':'validate'}).status_code,404)
    def test_optimistic_revision_and_review_conflicts(self):
        revision=self.link()
        with self.assertRaises(ValidationError):svc.save_revision(self.user,self.revision.document,self.revision.draft.snapshot,'TEST stale',1)
        svc.validate(self.user,revision);event=svc.review(self.user,revision,'REQUESTED','TEST request',0)
        with self.assertRaises(ValidationError):svc.review(self.user,revision,'CHANGES_REQUESTED','TEST stale',0)
    def test_actual_forms_api_edits_validation_and_output(self):
        response=self.client.get(reverse('market-ra-document',args=[self.revision.pk]));self.assertEqual(response.status_code,200)
        self.assertContains(response,'section-DESC')
        response=self.client.post(self.url,json.dumps({'action':'revise','expected':1,'reason':'TEST edit','body_DESC':'TEST revised body','model_DESC':'DEMO-MRI-1','refs_DESC':[]}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        url=reverse('market-ra-document-api',args=[response.json()['revision_id']])
        response=self.client.post(url,{'action':'validate'});self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['validation'])
        for kind in ('csv','docx'):
            out=self.client.get(reverse('market-ra-document-output',args=[response.json()['revision_id'],kind]));self.assertEqual(out.status_code,200)
            if kind=='csv':self.assertTrue(out.content.startswith(b'\xef\xbb\xbf'))
    def test_create_form_and_country_permissions(self):
        data={'device':self.device.pk,'template':self.template.pk,'document_type':'description','country':'US','language':'en','reason':'TEST create'}
        response=self.client.post(reverse('market-ra-documents-api'),data)
        self.assertEqual(response.status_code,201)
        data['country']='FR';response=self.client.post(reverse('market-ra-documents-api'),data);self.assertEqual(response.status_code,400)
    def test_invalid_external_adoption_is_rejected(self):
        with self.assertRaises(PermissionDenied):svc.edited_snapshot(self.user,self.revision,{'refs_DESC':[9999999]})
    def test_approval_requires_current_validation(self):
        revision=self.link();svc.validate(self.user,revision)
        self.fda('TEST-v2','TEST revised 510(k) source')
        with self.assertRaises(ValidationError):svc.review(self.user,revision,'REQUESTED','TEST',0)
    def test_removed_clause_is_detected(self):
        revision=self.link()
        self.fda('TEST-v2','III. Different Section\nTEST revised body with no old section.')
        self.assertTrue(svc.impacts(self.user,revision))

    def test_korean_creation_and_explicit_product_refresh(self):
        revision=svc.create_document(self.user,self.project,'description','US','ko-KR','TEST Korean')
        self.assertIn('등록 제품',revision.draft.snapshot['rows'][0]['body'])
        self.project.specification={**self.project.specification,'intended_use':'TEST revised intended use'};self.project.save()
        response=self.client.post(reverse('market-ra-document-api',args=[revision.pk]),{'action':'refresh','expected':1,'reason':'TEST product refresh'})
        self.assertEqual(response.status_code,201)
        updated=RADocumentRevision.objects.get(pk=response.json()['revision_id'])
        self.assertEqual(updated.draft.snapshot['specification']['intended_use'],'TEST revised intended use')
        revision.draft.refresh_from_db();self.assertEqual(revision.draft.snapshot['specification']['intended_use'],'DEMO internal test use')
    def test_approved_draft_becomes_review_needed_on_new_source(self):
        revision=self.link();svc.validate(self.user,revision)
        event=svc.review(self.user,revision,'REQUESTED','TEST',0)
        svc.review(self.user,revision,'APPROVED','TEST',event.pk,True)
        self.fda('TEST-v3','TEST changed scope')
        self.assertEqual(svc.effective_state(self.user,revision),'REVIEW_REQUIRED')
        self.assertEqual(svc.version_state(revision),'APPROVED')
    def test_old_draft_adoption_is_included_in_impact_list(self):
        revision=self.link();self.fda('TEST-v3','TEST changed scope')
        response=self.client.get(reverse('market-ra-impacts-api'))
        self.assertTrue(any(r['target']=='adoption' for r in response.json()['items']))
    def test_api_does_not_allow_snapshot_or_foreign_refs_injection(self):
        payload={'action':'revise','expected':1,'reason':'TEST','snapshot':{'fake':'injected'},'refs_DESC':[9999999]}
        self.assertEqual(self.client.post(self.url,json.dumps(payload),content_type='application/json').status_code,403)

    def test_legacy_export_uses_versioned_review_and_export(self):
        url=reverse('market-dental-output',args=[self.device.pk,self.revision.draft_id,'docx'])
        response=self.client.get(url)
        self.assertRedirects(response,reverse('market-ra-document-output',args=[self.revision.pk,'docx']))
    def test_eu_related_amendment_without_extracted_text_is_pending(self):
        from .eu_legal_models import EULegalDocument
        from .source_search import candidates
        source=next(r for r in candidates(self.user,jurisdiction='EU') if r['section']=='Article 87')
        EULegalDocument.objects.create(identifier='TEST-amendment',celex='TEST-amendment',title='TEST related amendment',official_url='https://eur-lex.europa.eu/test',source_type='eu_law',kind='eu_amendment',language='en',parent=self.eu,checked_on='2026-11-18',recorded_by=self.user)
        change=svc.change_for(self.user,source,candidates(self.user,include_history=True))
        self.assertIsNotNone(change);self.assertTrue(change['snapshot']['pending_version'])
    def test_revision_country_registration_revocation_hides_listing(self):
        ProductMarket.objects.filter(device=self.device,market='US').delete()
        self.assertFalse(svc.visible_documents(self.user).filter(pk=self.revision.document_id).exists())
        self.assertEqual(self.client.get(self.url).status_code,404)
