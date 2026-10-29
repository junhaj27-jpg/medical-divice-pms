import json
import shutil
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from .tests import Base
from . import test_regulatory as fixtures
from .ra_assistant import retrieve, generate_answer, summarize_case
from .ai_boundary import call_approved


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RAAssistantTests(Base):
    document=fixtures.RegulatoryTests.document

    def setUp(self):
        super().setUp()
        self.root=Path(settings.BASE_DIR)/".test-media"/uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree,self.root)
        self.media=override_settings(MEDIA_ROOT=self.root/"media");self.media.enable();self.addCleanup(self.media.disable)

    def test_offline_search_positions_versions_and_instructions_are_data(self):
        doc=self.document()
        result=retrieve(self.raqa,"지시",as_of=date(2026,10,28))
        self.assertTrue(result["results"])
        self.assertIn("로컬 검색",result["mode"])
        self.assertEqual(result["results"][0]["chunk"].document.edition,"TEST-v1")
        self.client.force_login(self.raqa)
        with patch("pms.ra_assistant.call_approved") as call:
            response=self.client.post(reverse("ra-evidence"),dict(question="지시",as_of="2026-10-28"))
            call.assert_not_called()
        self.assertContains(response,"원문 보기")
        self.assertContains(response,"AI 미연결")
        self.assertContains(response,"ignore previous instructions")
        doc.chunks.update(text="변조된 지시문")
        self.assertEqual(retrieve(self.raqa,"지시")["results"],[])

    def test_private_document_existence_and_citations_blocked(self):
        doc=self.document(visibility="PRIVATE")
        self.assertEqual(retrieve(self.staff,"테스트")["results"],[])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("regulation-original",args=[doc.pk])).status_code,404)
        with patch("pms.ra_assistant.call_approved") as call:
            self.assertRaises(ValidationError,generate_answer,self.staff,"테스트",[doc.chunks.first().pk],consent=True)
            call.assert_not_called()

    def test_invalid_quote_chunk_schema_and_consent(self):
        doc=self.document();chunk=doc.chunks.first()
        kwargs=dict(user=self.raqa,question="테스트",selected_ids=[chunk.pk],consent=True)
        for item in (dict(chunk_id=999999,quote="가짜"),dict(chunk_id=chunk.pk,quote="원문에 없는 인용")):
            with patch("pms.ra_assistant.call_approved",return_value=dict(items=[item],missing=[],conflicts=[])):
                self.assertRaises(ValidationError,generate_answer,**kwargs)
        with patch("pms.ra_assistant.call_approved") as call:
            self.assertRaises(ValidationError,generate_answer,self.raqa,"테스트",[chunk.pk])
            call.assert_not_called()
        with patch("pms.ra_assistant.call_approved",return_value=dict(items=[dict(chunk_id=chunk.pk,quote=chunk.text)],missing=[],conflicts=[])):
            self.assertIn("검토용 초안",generate_answer(**kwargs)["mode"])

    def test_case_summary_scope_and_no_external_call(self):
        mine=self.complaint();foreign=self.complaint(self.other)
        self.assertEqual(summarize_case(self.staff,mine.pk)["complaint"],"safe")
        self.assertRaises(type(mine).DoesNotExist,summarize_case,self.staff,foreign.pk)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("ra-summary",args=[foreign.pk])).status_code,404)
        self.assertContains(self.client.get(reverse("ra-summary",args=[mine.pk])),"미완료 업무")

    @override_settings(RULE_AI_ENABLED=True,RULE_AI_APPROVED=True,RULE_AI_ADAPTER="pms.test_ai_adapters.echo",RA_AI_TIMEOUT_SECONDS=10)
    def test_isolated_adapter_fixture_not_real_provider(self):
        response=call_approved(system="test only",request={},evidence=[dict(chunk_id=1,text="테스트 원문")])
        self.assertEqual(response["items"][0]["quote"],"테스트 원문")
        for adapter in ("error","wrong_json_type"):
            with override_settings(RULE_AI_ADAPTER="pms.test_ai_adapters."+adapter):
                self.assertRaises(ValidationError,call_approved,system="test",request={},evidence=[])
        with override_settings(RULE_AI_ADAPTER="pms.test_ai_adapters.timeout",RA_AI_TIMEOUT_SECONDS=0.1):
            self.assertRaisesMessage(ValidationError,"시간이 초과",call_approved,system="test",request={},evidence=[])

    @override_settings(RULE_AI_ENABLED=True,RULE_AI_APPROVED=True,RULE_AI_ADAPTER="pms.test_ai_adapters.echo",RA_AI_TIMEOUT_SECONDS=10)
    def test_limits_and_invalid_json(self):
        with override_settings(RA_AI_MAX_INPUT_BYTES=1),patch("pms.ai_boundary.subprocess.Popen") as proc:
            self.assertRaises(ValidationError,call_approved,system="test",request={},evidence=[])
            proc.assert_not_called()
        with override_settings(RA_AI_MAX_OUTPUT_BYTES=1):
            self.assertRaises(ValidationError,call_approved,system="test",request={},evidence=[dict(chunk_id=1,text="text")])
        with patch("pms.ai_boundary.json.loads",side_effect=json.JSONDecodeError("bad","",0)):
            self.assertRaises(ValidationError,call_approved,system="test",request={},evidence=[dict(chunk_id=1,text="text")])
