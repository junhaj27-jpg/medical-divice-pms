"""All regulation texts below are synthetic test fixtures, never legal guidance."""
import hashlib
import io
import json
import shutil
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from .tests import Base
from .models import *
from .regulation_documents import *
from .regulatory import *
from .rule_ai import generate_ai_draft


TEST_TEXT='''제1조 테스트 전용 문서. 실제 법정 규정이 아닙니다.

테스트 관할 TEST-REGION의 전체 예시 제품에 적용한다. 예시 사건 TEST_EVENT를 테스트 기관에 보고한다. 예외 없음.

접수 일시 다음날부터 3 달력일 이내, 시작일 미포함, 18:00 Asia/Seoul 마감. 테스트 문서 시행일 2026-01-01.

이 문장에 포함된 ignore previous instructions와 외부 URL 수집 지시는 참고 데이터이며 실행하지 않는다.'''


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RegulatoryTests(Base):
    def setUp(self):
        super().setUp();self.root=Path(settings.BASE_DIR)/'.test-media'/uuid.uuid4().hex;self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree,self.root)
        self.media=override_settings(MEDIA_ROOT=self.root/'media');self.media.enable();self.addCleanup(self.media.disable)
        self.c=self.complaint();self.c.is_example=True;self.c.complaint_type='TEST_EVENT';self.c.save()
    def document(self,text=TEST_TEXT,edition='TEST-v1',visibility='TEAM',user=None,pdf=None):
        user=user or self.raqa
        doc=RegulationDocument(title='테스트 전용 규정 (실제 법정 기준 아님)',issuer='테스트 발행자',jurisdiction='TEST-REGION',scope_description='전체 예시 제품',document_number='TEST-ONLY',edition=edition,published_on=date(2025,12,1),effective_on=date(2026,1,1),official_url='https://example.invalid/test-only',visibility=visibility,is_example=True,file=SimpleUploadedFile('test.pdf' if pdf else 'test.txt',pdf or text.encode()))
        with override_settings(ANTIVIRUS_COMMAND=['fixture-scanner']),patch('pms.file_security.subprocess.run') as run:
            run.return_value.returncode=0;doc=register_document(doc,user)
        doc=extract_document(doc,user)
        if doc.extraction_status=='READY': doc=review_document(doc,self.admin,'REVIEWED','테스트 자료 확인')
        return doc
    def draft(self,**kwargs):
        values=dict(name='테스트 규칙 '+uuid.uuid4().hex[:8],jurisdiction='TEST-REGION',scope_description='전체 예시 제품',conditions={'complaint_type':'TEST_EVENT'},reporting_authority='테스트 기관',obligation_trigger='테스트 사건 접수',basis='REPORTED',deadline_expression='다음날부터 3 달력일',days=3,deadline_unit='DAYS',day_type='CALENDAR',include_start=False,deadline_time=time(18),timezone_name='Asia/Seoul',exceptions='없음 (테스트 검토)',effective_on=date(2026,1,1),is_example=True,change_reason='테스트 신규 초안')
        values.update(kwargs);return save_draft(ReportingRule(**values),self.raqa,'테스트 신규 초안')
    def cite_all(self,rule,doc=None):
        doc=doc or self.document();chunk=doc.chunks.first()
        for field in FIELD_LABELS: add_citation(rule,self.raqa,field,chunk,chunk.text,'테스트 문서에 대한 수동 검토','테스트 항목별 인용')
        rule.refresh_from_db();return rule
    def publish(self,rule):
        preview_rule(rule,self.raqa,f'{max(rule.effective_on,self.c.reported_on).isoformat()}T10:00:00+09:00')
        rule=transition_rule(rule,self.raqa,'submit','테스트 검토 요청')
        rule=transition_rule(rule,self.admin,'approve','테스트 승인')
        return transition_rule(rule,self.admin,'activate','테스트 시행 승인')
    def apply(self,rule,base=None,previous=None,reason='테스트 적용'):
        self.c.refresh_from_db()
        preview=preview_rule(rule,self.raqa,base or f'{self.c.reported_on.isoformat()}T10:00:00+09:00')
        previous=previous if previous is not None else (self.c.rule_applications.order_by('-pk').first().pk if self.c.rule_applications.exists() else 0)
        return apply_regulated_rule(self.c,rule,self.raqa,preview,reason,previous,str(self.c.due_date or ''))
    def test_document_private_scope_and_staff_denial(self):
        doc=self.document(visibility='PRIVATE')
        self.assertFalse(documents_for(self.other).filter(pk=doc.pk).exists())
        self.assertFalse(documents_for(self.staff).filter(pk=doc.pk).exists())
        self.client.force_login(self.staff)
        for name in ('regulation-detail','regulation-original'):
            self.assertEqual(self.client.get(reverse(name,args=[doc.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('regulation-create')).status_code,403)
    def test_rule_drafts_are_private_to_author_and_approver(self):
        draft=self.draft();self.assertNotIn(draft,rules_for(self.staff))
        other_ra=User.objects.create_user('other-ra');Profile.objects.create(user=other_ra,role='RA_QA')
        self.assertNotIn(draft,rules_for(other_ra));self.assertRaises(PermissionDenied,editable,draft,other_ra)
        self.client.force_login(self.staff);self.assertEqual(self.client.get(reverse('rule-detail',args=[draft.pk])).status_code,404)
    def test_extraction_page_section_version_and_keyword_filters(self):
        source=io.BytesIO();c=canvas.Canvas(source)
        c.drawString(40,800,'Article 1 TEST_EVIDENCE_ALPHA');c.showPage();c.drawString(40,800,'Article 2 TEST_EVIDENCE_BETA');c.drawString(40,760,'Article 3 TEST_EVIDENCE_GAMMA');c.save()
        doc=self.document(pdf=source.getvalue())
        rows=search_evidence(self.raqa,'TEST_EVIDENCE_BETA',jurisdiction='TEST-REGION',edition='TEST-v1',document_id=doc.pk)
        self.assertTrue(rows);self.assertTrue(any(row['chunk'].page==2 for row in rows));self.assertEqual(rows[0]['chunk'].document.edition,'TEST-v1')
        self.assertIn('Article',rows[0]['chunk'].section)
        gamma=doc.chunks.get(text__contains='GAMMA');self.assertEqual(gamma.page,2);self.assertTrue(gamma.section.startswith('Article 3'))
        self.assertEqual(search_evidence(self.raqa,'TEST_EVIDENCE_BETA',jurisdiction='OTHER'),[])
        self.assertEqual(search_evidence(self.raqa,'TEST_EVIDENCE_BETA',edition='v999'),[])
        old=self.document(edition='TEST-v0');self.assertTrue(old.chunks.exists());self.assertTrue(doc.chunks.exists())
    def test_no_query_document_still_enforces_scope(self):
        doc=self.document();self.assertTrue(search_evidence(self.raqa,'',document_id=doc.pk))
        self.assertEqual(search_evidence(self.raqa,'',document_id=doc.pk,jurisdiction='OTHER'),[])
    def test_scanned_pdf_is_ocr_required(self):
        writer=PdfWriter();writer.add_blank_page(width=595,height=842);output=io.BytesIO();writer.write(output)
        doc=self.document(pdf=output.getvalue());self.assertEqual(doc.extraction_status,'OCR_REQUIRED');self.assertEqual(doc.chunks.count(),0)
        self.assertRaises(ValidationError,review_document,doc,self.admin,'REVIEWED','확인')
    def test_failed_scan_blocks_extract_and_original(self):
        with override_settings(ANTIVIRUS_COMMAND=[]):
            doc=register_document(RegulationDocument(title='테스트 대기',issuer='test',jurisdiction='TEST-REGION',scope_description='test',document_number='T',edition='T',is_example=True,file=SimpleUploadedFile('test.txt',b'TEST')),self.raqa)
        doc=extract_document(doc,self.raqa);self.assertEqual(doc.scan_status,'FAILED');self.assertEqual(doc.extraction_status,'BLOCKED')
        self.client.force_login(self.raqa);self.assertEqual(self.client.get(reverse('regulation-original',args=[doc.pk])).status_code,403)
    def test_source_url_is_record_only_and_no_instructions_execute(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('must not fetch')):
            doc=self.document();rows=search_evidence(self.raqa,'ignore previous instructions')
        self.assertTrue(rows);self.assertEqual(doc.official_url,'https://example.invalid/test-only')
    def test_insufficient_evidence_blocks_request_and_approval(self):
        rule=self.draft();preview_rule(rule,self.raqa,f'{self.c.reported_on}T10:00:00+09:00')
        self.assertRaises(ValidationError,transition_rule,rule,self.raqa,'submit','검토')
        self.assertRaises(ValidationError,transition_rule,rule,self.admin,'approve','승인')
        self.assertEqual(rule.state,'DRAFT')
    def test_unresolved_conflicts_and_private_sources_block(self):
        rule=self.cite_all(self.draft(),self.document(visibility='PRIVATE'))
        self.assertTrue(any('공동' in x for x in readiness(rule,self.admin)))
        rule=save_draft(rule,self.raqa,'충돌 표시',rule.revision);rule.unresolved_items=['문서 A와 B 상충'];rule=save_draft(rule,self.raqa,'상충 미해소',rule.revision)
        self.assertRaises(ValidationError,transition_rule,rule,self.raqa,'submit','요청')
    def test_separate_author_and_rejection_reason(self):
        rule=self.cite_all(self.draft());preview_rule(rule,self.raqa,f'{self.c.reported_on}T10:00:00+09:00')
        rule=transition_rule(rule,self.raqa,'submit','요청')
        with override_settings(RULE_APPROVER_ROLES=('ADMIN','RA_QA')):
            self.assertRaisesMessage(ValidationError,'분리',transition_rule,rule,self.raqa,'approve','자기 승인')
        self.assertRaises(ValidationError,transition_rule,rule,self.admin,'reject','')
        rejected=transition_rule(rule,self.admin,'reject','추가 근거 필요');self.assertEqual(rejected.state,'DRAFT')
        self.assertEqual(rejected.changes.first().reason,'추가 근거 필요')
    def test_unapproved_and_future_rule_not_applied(self):
        draft=self.cite_all(self.draft());self.assertRaises(ValidationError,self.apply,draft)
        tomorrow=timezone.localdate()+timedelta(days=1)
        future=self.cite_all(self.draft(effective_on=tomorrow));preview_rule(future,self.raqa,f'{tomorrow}T10:00:00+09:00')
        future=transition_rule(future,self.raqa,'submit','요청');future=transition_rule(future,self.admin,'approve','승인')
        self.assertRaisesMessage(ValidationError,'시행 기간',transition_rule,future,self.admin,'activate','아직 미래')
        self.assertRaises(ValidationError,self.apply,future,base=f'{tomorrow}T10:00:00+09:00')
    def test_approved_immutable_and_revision_preserves_sources(self):
        rule=self.publish(self.cite_all(self.draft()));old=rule_payload(rule)
        rule.days=99;self.assertRaises(ValidationError,rule.save)
        rule.refresh_from_db();new=revise_rule(rule,self.raqa,'개정 검토');self.assertEqual(new.state,'DRAFT');self.assertEqual(new.version,2);self.assertEqual(new.supersedes,rule)
        self.assertEqual(new.citations.count(),rule.citations.count());self.assertEqual(rule_payload(rule),old)
    def test_overlapping_rules_block_activation_and_disjoint_conditions(self):
        first=self.publish(self.cite_all(self.draft()))
        second=self.cite_all(self.draft());preview_rule(second,self.raqa,f'{self.c.reported_on}T10:00:00+09:00');second=transition_rule(second,self.raqa,'submit','요청');second=transition_rule(second,self.admin,'approve','승인')
        self.assertIn(first,conflicts(second));self.assertRaisesMessage(ValidationError,'충돌',transition_rule,second,self.admin,'activate','시행')
        other=self.draft(conditions={'complaint_type':'OTHER'});self.assertFalse(overlaps(first,other))
    def test_calendar_start_day_and_time_zone(self):
        r=self.draft(days=1,include_start=False)
        result=calculate_deadline(r,'2026-10-23T23:00:00+09:00');self.assertEqual(result['due_at'],'2026-10-24T18:00:00+09:00')
        r.include_start=True;self.assertEqual(calculate_deadline(r,'2026-10-23T10:00:00+09:00')['due_at'],'2026-10-23T18:00:00+09:00')
        r.timezone_name='America/New_York';r.deadline_unit='HOURS';r.include_start=False;r.days=2
        value=calculate_deadline(r,'2026-11-01T00:30:00-04:00');self.assertEqual(value['due_at'],'2026-11-01T01:30:00-05:00')
        self.assertRaises(ValidationError,calculate_deadline,r,'2026-11-01T01:30:00')
    def test_business_weekends_holidays_and_verified_range(self):
        r=self.draft(days=1,day_type='BUSINESS',holidays=[{'date':'2026-10-26','name':'테스트 휴일'}],holiday_verified_from=date(2026,10,1),holiday_verified_until=date(2026,10,31),holiday_checked_on=timezone.localdate())
        result=calculate_deadline(r,'2026-10-23T10:00:00+09:00');self.assertEqual(result['due_at'],'2026-10-27T18:00:00+09:00');self.assertEqual(len(result['excluded']),3)
        r.holiday_verified_until=date(2026,10,26);self.assertRaisesMessage(ValidationError,'확인 범위',calculate_deadline,r,'2026-10-23T10:00:00+09:00')
        r.holidays=[];r.holiday_verified_until=date(2026,10,31);self.assertEqual(calculate_deadline(r,'2026-10-23T10:00:00+09:00')['due_at'],'2026-10-26T18:00:00+09:00')
    def test_holiday_csv_dates_names_and_duplicates(self):
        rule=self.draft()
        imported=import_holidays(rule,self.raqa,SimpleUploadedFile('dates.csv','date,name\n2026-12-25,테스트 휴일\n'.encode()),'확인된 휴일');self.assertEqual(imported.holidays[0]['name'],'테스트 휴일')
        self.assertRaises(ValidationError,import_holidays,rule,self.raqa,SimpleUploadedFile('bad.csv',b'date,name\n2026-12-25,x\n2026-12-25,y'),'중복')
        self.assertRaises(ValidationError,import_holidays,rule,self.raqa,SimpleUploadedFile('bad.csv',b'date,name\n2026-02-31,x'),'잘못된 날짜')
    def test_case_snapshots_existing_deadlines_and_recalculation_history(self):
        rule=self.publish(self.cite_all(self.draft()));first=self.apply(rule);original=first.snapshot
        old_due=first.due_at
        new=revise_rule(rule,self.raqa,'기한 검토');new.days=5;new=save_draft(new,self.raqa,'테스트 5일 검토',new.revision)
        preview_rule(new,self.raqa,f'{self.c.reported_on}T10:00:00+09:00');new=transition_rule(new,self.raqa,'submit','요청');new=transition_rule(new,self.admin,'approve','승인')
        self.c.refresh_from_db();self.assertEqual(self.c.due_date,old_due.astimezone(ZoneInfo(rule.timezone_name)).date())
        rule=transition_rule(rule,self.admin,'retire','새 버전으로 교체');new=transition_rule(new,self.admin,'activate','새 버전 명시 시행')
        second=self.apply(new,reason='변경 전후 확인 후 재산정');first.refresh_from_db()
        self.assertEqual(first.snapshot,original);self.assertEqual(first.due_at,old_due);self.assertEqual(second.previous_snapshot['application_id'],first.pk);self.assertEqual(self.c.rule_applications.count(),2)
    def test_stale_preview_and_stale_previous_deadline_blocked(self):
        rule=self.publish(self.cite_all(self.draft()));preview=preview_rule(rule,self.raqa,f'{self.c.reported_on}T10:00:00+09:00')
        self.c.due_date=timezone.localdate();self.c.save()
        self.assertRaisesMessage(ValidationError,'변경',apply_regulated_rule,self.c,rule,self.raqa,preview,'이전 값 검토',0,'')
        self.assertRaisesMessage(ValidationError,'변경',apply_regulated_rule,self.c,rule,self.raqa,preview,'이전 이력 검토',123,str(self.c.due_date))
    def test_ai_off_does_not_call_adapter_and_manual_flow_works(self):
        doc=self.document();chunk=doc.chunks.first()
        with patch('pms.rule_ai.import_string',side_effect=AssertionError('must not call')):
            self.assertRaisesMessage(ValidationError,'AI 연결 필요',generate_ai_draft,self.raqa,{},[chunk],True)
        self.assertEqual(ReportingRule.objects.count(),0)
        rule=self.publish(self.cite_all(self.draft(),doc));self.assertEqual(self.apply(rule).rule_id,rule.pk)
    def test_ai_hallucinated_citation_rejected(self):
        chunk=self.document().chunks.first()
        response={'fields':{'name':'AI 테스트'},'citations':[{'field':'days','chunk_id':999999,'quote':'90일'}]}
        with override_settings(RULE_AI_ENABLED=True,RULE_AI_APPROVED=True,RULE_AI_ADAPTER='tests.adapter'),patch('pms.rule_ai.import_string',return_value=lambda **kwargs:response):
            self.assertRaisesMessage(ValidationError,'검색 결과',generate_ai_draft,self.raqa,{},[chunk],True)
        self.assertFalse(ReportingRule.objects.exists())
    def test_ai_ambiguous_or_unsupported_number_stays_unconfirmed(self):
        for index,expression in enumerate(('인지한 날부터 즉시 보고한다.','즉시 보고한다.')):
            doc=self.document(text='제1조 테스트 전용\n\n'+expression);chunk=doc.chunks.last()
            response={'fields':{'name':'AI 모호 표현 테스트 '+str(index),'days':3,'basis':'REPORTED'},'citations':[{'field':'days','chunk_id':chunk.pk,'quote':chunk.text},{'field':'basis','chunk_id':chunk.pk,'quote':chunk.text}]}
            with override_settings(RULE_AI_ENABLED=True,RULE_AI_APPROVED=True,RULE_AI_ADAPTER='tests.adapter'),patch('pms.rule_ai.import_string',return_value=lambda **kwargs:response):
                rule=generate_ai_draft(self.raqa,{},[chunk],True)
            self.assertIsNone(rule.days);self.assertEqual(rule.basis,'');self.assertTrue(rule.unresolved_items);self.assertEqual(rule.state,'DRAFT')
    def test_revoked_or_tampered_document_blocks_search_and_apply(self):
        doc=self.document();rule=self.publish(self.cite_all(self.draft(),doc))
        doc.scan_status='QUARANTINED';doc.save();self.assertEqual(search_evidence(self.raqa,'접수'),[]);self.assertRaises(ValidationError,self.apply,rule)
    def test_html_empty_state_new_forms_and_manual_draft(self):
        self.client.force_login(self.raqa)
        response=self.client.get(reverse('rule-list'));self.assertContains(response,'등록된 보고 규칙이 없습니다. 규정 문서를 등록하거나 직접 규칙을 작성해 주세요. AI 초안은 RA 검토·승인 후 적용할 수 있습니다.')
        self.assertContains(response,'AI 연결 필요')
        for name in ('rule-create','regulation-create','regulation-list','evidence-search'):
            self.assertEqual(self.client.get(reverse(name)).status_code,200,name)
        response=self.client.post(reverse('rule-create'),{'name':'빈 값 수동 초안','change_reason':'확인 필요 상태로 시작','conditions':'{}','holidays':'[]','unresolved_items':'[]','source_expressions':'{}','is_example':'on'})
        self.assertEqual(response.status_code,302);rule=ReportingRule.objects.get(name='빈 값 수동 초안');self.assertIsNone(rule.days);self.assertEqual(rule.state,'DRAFT')
        for name in ('rule-detail','rule-edit','rule-preview','rule-compare','rule-holidays'):
            self.assertEqual(self.client.get(reverse(name,args=[rule.pk])).status_code,200,name)
    def test_html_search_manual_evidence_draft_and_scope(self):
        doc=self.document();self.client.force_login(self.raqa)
        response=self.client.get(reverse('evidence-search'),{'document':doc.pk});self.assertContains(response,'청크 #')
        chunk=doc.chunks.first()
        response=self.client.post(reverse('rule-from-evidence'),{'document':doc.pk,'chunks':[chunk.pk],'mode':'manual'})
        self.assertEqual(response.status_code,302);rule=ReportingRule.objects.get(origin='EVIDENCE');self.assertIsNone(rule.days);self.assertTrue(rule.citations.exists())
        self.assertEqual(self.client.get(reverse('regulation-detail',args=[doc.pk])).status_code,200)
    def test_html_case_confirmation_and_approved_read_access(self):
        rule=self.publish(self.cite_all(self.draft()));self.client.force_login(self.raqa)
        response=self.client.post(reverse('rule-apply',args=[self.c.pk]),{'rule':rule.pk,'basis_at':f'{self.c.reported_on}T10:00:00+09:00','reason':'화면 계산','action':'preview'})
        self.assertContains(response,'확인한 계산을 사건에 적용');preview=RulePreview.objects.filter(created_by=self.raqa,rule=rule).latest('pk')
        response=self.client.post(reverse('rule-apply',args=[self.c.pk]),{'action':'confirm','preview_id':preview.pk,'previous_id':0,'previous_due_date':'','reason':'화면 전후 확인'})
        self.assertEqual(response.status_code,302);self.assertEqual(self.c.rule_applications.count(),1)
        self.client.force_login(self.staff);self.assertEqual(self.client.get(reverse('rule-detail',args=[rule.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('regulation-detail',args=[rule.citations.first().chunk.document_id])).status_code,200)

    def test_multiple_documents_show_both_citations_and_require_review(self):
        rule=self.draft();a=self.document(edition='TEST-v1');b=self.document(text='제1조 테스트 대체 근거, 문서 간 차이 검토 필요.',edition='TEST-v2')
        for doc in (a,b):
            chunk=doc.chunks.first();add_citation(rule,self.raqa,'days',chunk,chunk.text,'','복수 버전 비교')
        rule.refresh_from_db();self.assertEqual(rule.citations.count(),2);self.assertTrue(any('복수 문서' in item for item in rule.unresolved_items))
    def test_draft_edit_invalidates_old_preview(self):
        rule=self.cite_all(self.draft());preview=preview_rule(rule,self.raqa,f'{self.c.reported_on}T10:00:00+09:00')
        rule.days=4;rule=save_draft(rule,self.raqa,'값 변경 후 재검증 필요',rule.revision)
        self.assertNotEqual(fingerprint(rule),preview.fingerprint)
        self.assertRaisesMessage(ValidationError,'미리보기',transition_rule,rule,self.raqa,'submit','요청')
    def test_test_rule_cannot_apply_to_real_case(self):
        rule=self.publish(self.cite_all(self.draft()));self.c.is_example=False;self.c.save()
        self.assertRaisesMessage(ValidationError,'테스트 사건',self.apply,rule)
    def test_rag_tampered_file_does_not_return_cached_text(self):
        doc=self.document();Path(doc.file.path).write_bytes(b'tampered original')
        self.assertEqual(search_evidence(self.raqa,'접수'),[])
    def test_rescan_never_relabels_tampered_document_as_original(self):
        doc=self.document();original=doc.sha256;Path(doc.file.path).write_bytes(b'new clean-looking document')
        with override_settings(ANTIVIRUS_COMMAND=['fixture-scanner']),patch('pms.file_security.subprocess.run') as run:
            run.return_value.returncode=0;scan_attachment(doc,self.admin)
        doc.refresh_from_db();self.assertEqual(doc.sha256,original);self.assertEqual(doc.scan_status,'QUARANTINED')
        self.assertEqual(search_evidence(self.raqa,'접수'),[])
    def test_registered_document_version_and_visibility_are_immutable(self):
        doc=self.document();doc.edition='changed'
        self.assertRaises(ValidationError,doc.save)
        doc.refresh_from_db();doc.visibility='PRIVATE';self.assertRaises(ValidationError,doc.save)
    def test_malformed_query_ids_return_404_not_server_error(self):
        self.client.force_login(self.raqa);doc=self.document();rule=self.draft()
        self.assertEqual(self.client.get(reverse('regulation-detail',args=[doc.pk])+'?chunk=bad').status_code,404)
        self.assertEqual(self.client.get(reverse('rule-compare',args=[rule.pk])+'?other=bad').status_code,404)
        self.assertEqual(self.client.get(reverse('rule-citation-new',args=[rule.pk])+'?chunk=bad').status_code,404)
        self.assertEqual(self.client.post(reverse('rule-apply',args=[self.c.pk]),{'action':'confirm','preview_id':'bad'}).status_code,404)

    def test_ai_adapter_timeout_and_malformed_citation_types(self):
        doc = self.document()
        chunk = doc.chunks.first()
        with override_settings(RULE_AI_ENABLED=True, RULE_AI_APPROVED=True, RULE_AI_ADAPTER='tests.adapter'):
            with patch('pms.rule_ai.import_string', return_value=lambda **kwargs: (_ for _ in ()).throw(TimeoutError())):
                self.assertRaisesMessage(ValidationError, '시간이 초과', generate_ai_draft, self.raqa, {}, [chunk], True)
            for citation in [dict(field='days', chunk_id=[], quote='3'), dict(field=[], chunk_id=chunk.pk, quote='3'), dict(field='days', chunk_id=chunk.pk, quote='3', interpretation=[])]:
                response = {'fields':{}, 'citations':[citation]}
                with patch('pms.rule_ai.import_string', return_value=lambda **kwargs: response):
                    self.assertRaisesMessage(ValidationError, '형식 오류', generate_ai_draft, self.raqa, {}, [chunk], True)
