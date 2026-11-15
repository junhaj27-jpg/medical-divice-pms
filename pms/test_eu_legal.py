from datetime import date
from copy import deepcopy
from zipfile import ZipFile
import io

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from .dental_models import DentalProject, WritingTemplate
from .eu_legal_models import EULegalDocument, EUProjectLaw, EUImpactConfirmation
from .market_models import MarketAccess, ProductMarket
from .models import Attachment, ControlledDocument, RegulatoryProfile
from .ra_services import save_record
from .test_dental import DentalTests


class EULegalTests(DentalTests):
    def setUp(self):
        super().setUp()
        MarketAccess.objects.filter(pk=self.access.pk).update(markets=["US", "DE"])
        ProductMarket.objects.create(device=self.device, market="DE", is_example=True)
        self.register = reverse("market-eu-documents")
        self.eu_url = reverse("market-eu-writing", args=[self.device.pk])
        self.law_data = {
            "action": "register", "celex": "32017R0745", "title": "Regulation (EU) 2017/745",
            "source_type": "eu_law", "kind": "eu_oj", "oj_reference": "OJ L 117, 5.5.2017, p.1",
            "published_on": "2017-05-05", "language": "en", "checked_on": "2026-11-15",
        }

    def law_and_project(self):
        self.assertEqual(self.client.post(self.register, self.law_data).status_code, 302)
        doc = EULegalDocument.objects.get()
        template = WritingTemplate.objects.get(key="eu-mdr")
        data = {**self.spec, "regulation": "MDR", "template_id": template.pk,
                "users": "Clinicians", "environment": "Clinic", "product_version": "DEMO-v1"}
        self.assertEqual(self.client.post(self.eu_url, data).status_code, 302)
        project = DentalProject.objects.get(device=self.device, market="EU")
        self.assertEqual(self.client.post(self.eu_url, {
            "action": "law_link", "section": "EU.II.1", "document_id": doc.pk, "clause": "Annex II, section 1",
        }).status_code, 302)
        link = project.legal_links.get()
        self.assertEqual(self.client.post(self.eu_url, {"action": "law_review", "link_id": link.pk,
            "decision": "hs_applies", "reason": "DEMO RA scope review", "previous": 0}).status_code, 302)
        return doc, project

    def test_registration_duplicates_fallback_dates_and_languages(self):
        self.assertContains(self.client.get(self.register), "https://eur-lex.europa.eu/TodayOJ/index.html")
        self.assertContains(self.client.post(self.register, {"action": "lookup"}), "자동 조회를 사용할 수 없습니다")
        self.assertContains(self.client.post(self.register, {**self.law_data, "celex": "",
                           "official_url": "https://eur-lex.europa.eu/TodayOJ/index.html"}), "CELEX", status_code=400)
        self.client.post(self.register, self.law_data)
        doc = EULegalDocument.objects.get()
        self.assertIsNone(doc.effective_on)
        self.assertIsNone(doc.applies_on)
        self.assertRedirects(self.client.post(self.register, {**self.law_data, "celex": "",
                              "official_url": "https://eur-lex.europa.eu/eli/reg/2017/745/oj"}), reverse("market-eu-document", args=[doc.pk]))
        self.assertEqual(EULegalDocument.objects.count(), 1)
        url = reverse("market-eu-document", args=[doc.pk])
        self.assertContains(self.client.get(url), "/DE/TXT/")
        self.assertContains(self.client.get(url), "/FR/TXT/")
        original = (doc.celex, doc.language, doc.official_url)
        self.client.post(reverse("market-language"), {"language": "de-DE", "next": url})
        self.assertContains(self.client.get(url), "Regulation (EU) 2017/745")
        doc.refresh_from_db()
        self.assertEqual((doc.celex, doc.language, doc.official_url), original)

    def test_harmonised_standard_records_publication_scope_and_restriction(self):
        data = {**self.law_data, "celex": "32021D1182", "title": "Implementing Decision (EU) 2021/1182",
                "source_type": "eu_standard_oj", "published_on": ""}
        self.client.post(self.register, data)
        doc = EULegalDocument.objects.get()
        url = reverse("market-product-standards", args=[self.device.pk])
        payload = {"regulation": "MDR", "standard_number": "DEMO-STD", "edition": "DEMO-v1",
                   "eurlex_url": "https://eur-lex.europa.eu/eli/dec_impl/2021/1182/oj",
                   "decision_number": "2021/1182", "decision_item": "DEMO item",
                   "checked_on": "2026-11-15", "oj_document": doc.pk, "publication_scope": "DEMO limited scope",
                   "restrictions": "DEMO restrictions", "applicability": "hs_pending",
                   "applicability_reason": "DEMO RA assessment", "review_date": "2026-11-15"}
        self.assertRedirects(self.client.post(url, payload), url)
        record = self.device.harmonised_reviews.get()
        self.assertEqual((record.oj_document_id, record.publication_scope, record.restrictions),
                         (doc.pk, "DEMO limited scope", "DEMO restrictions"))
        self.assertContains(self.client.get(url), "DEMO restrictions")

    def test_ivdr_and_unconfirmed_collection_scope(self):
        from .dental_workflow import ready
        template = WritingTemplate.objects.get(key="eu-ivdr")
        data = {**self.spec, "regulation": "IVDR", "template_id": template.pk,
                "users": "Laboratory professionals", "environment": "Laboratory", "product_version": "DEMO-v1"}
        self.assertEqual(self.client.post(self.eu_url, data).status_code, 302)
        project = DentalProject.objects.get(device=self.device, market="EU")
        self.assertEqual(project.template_id, template.pk)
        self.assertFalse(ready(project))  # RA legal review is still required.
        self.client.post(self.register, {**self.law_data, "celex": "32017R0746", "title": "Regulation (EU) 2017/746"})
        doc = EULegalDocument.objects.get()
        link = project.legal_links.create(section="EU.II.1", document=doc, clause="Annex II, section 1", actor=self.user)
        link.reviews.create(decision="hs_applies", reason="DEMO IVDR scope", actor=self.user)
        self.assertTrue(ready(project))
        self.assertEqual(self.client.post(self.eu_url, {"action": "generate"}).status_code, 302)
        self.assertEqual(project.drafts.get().snapshot["market"], "EU")
        self.client.post(self.eu_url, {"action": "template", "template_id": WritingTemplate.objects.get(key="eu-common").pk})
        project.refresh_from_db()
        self.assertFalse(ready(project))

    def test_law_product_evidence_export_and_confirmed_revision_impact(self):
        # Existing US project and drafts remain separately addressable.
        self.client.post(self.url, self.spec)
        self.client.post(self.url, {"action": "generate"})
        us_project = DentalProject.objects.get(device=self.device, market="US")
        us_before = deepcopy(us_project.drafts.get().snapshot)
        doc, project = self.law_and_project()
        us_doc = self.document()
        self.assertEqual(self.client.post(self.eu_url, {"action": "evidence", "document": us_doc.pk,
            "section": "EU.II.1", "page": 1, "excerpt": "Optical test data.", "model": "DEMO-01"}).status_code, 400)
        profile = save_record(RegulatoryProfile(), self.user, dict(
            device=self.device, jurisdiction="EU", organization=self.profile.organization, organization_role="MANUFACTURER",
            title="DEMO EU", owner=self.user, is_example=True), "DEMO")
        file = Attachment.objects.create(ra_profile=profile, uploaded_by=self.user, file=us_doc.primary_file.file.name,
                                         scan_status="PASSED", sha256=us_doc.primary_file.sha256)
        evidence = save_record(ControlledDocument(), self.user, dict(
            profile=profile, owner=self.user, title="DEMO EU specification", category="TECHNICAL", number="DEMO-EU-SPEC",
            version=1, primary_file=file, change_reason="DEMO", is_example=True), "DEMO")
        self.assertEqual(self.client.post(self.eu_url, {"action": "evidence", "document": evidence.pk,
            "section": "EU.II.1", "page": 1, "excerpt": "Optical test data.", "model": "DEMO-01"}).status_code, 302)
        self.assertEqual(self.client.post(self.eu_url, {"action": "generate"}).status_code, 302)
        draft = project.drafts.get()
        original = deepcopy(draft.snapshot)
        self.assertEqual(original["rows"][0]["legal_references"][0]["celex"], doc.celex)
        output = lambda kind: reverse("market-dental-output", args=[self.device.pk, draft.pk, kind])
        data = b"".join(self.client.get(output("docx")).streaming_content)
        xml = ZipFile(io.BytesIO(data)).read("word/document.xml").decode()
        self.assertIn("Draft for RA Review", xml)
        self.assertIn("Annex II, section 1", xml)
        self.assertIn("DEMO-EU-SPEC v1 / p.1", xml)
        self.assertNotIn("eSTAR preparation", xml)
        csv = b"".join(self.client.get(output("matrix")).streaming_content).decode("utf-8-sig")
        self.assertIn("한국어 참고용", csv)
        self.assertIn(doc.celex, csv)
        self.assertIn("DEMO-EU-SPEC", csv)
        self.assertEqual(self.client.post(output("review"), {"note": "DEMO EU review"}).status_code, 302)
        revision_data = {**self.law_data, "celex": "32023R0607", "title": "Regulation (EU) 2023/607",
                         "kind": "eu_amendment", "parent": doc.pk, "published_on": ""}
        self.assertEqual(self.client.post(self.register, revision_data).status_code, 302)
        revision = EULegalDocument.objects.get(celex="32023R0607")
        detail = reverse("market-eu-document", args=[revision.pk])
        self.assertContains(self.client.get(detail), "EU.II.1")
        self.assertFalse(EUImpactConfirmation.objects.exists())
        link = project.legal_links.get()
        self.assertEqual(self.client.post(detail, {"action": "confirm_impact", "link": [link.pk],
                                                   "reason": "DEMO impact review"}).status_code, 302)
        self.assertContains(self.client.get(self.eu_url), "재검토 필요")
        self.assertContains(self.client.get(detail), "DEMO impact review")
        self.assertEqual(self.client.post(output("review"), {"note": "Old version"}).status_code, 400)
        draft.refresh_from_db()
        self.assertEqual(draft.snapshot, original)
        us_project.refresh_from_db()
        self.assertEqual(us_project.drafts.get().snapshot, us_before)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.post(reverse("market-language"), {"language": "en", "next": self.eu_url})
        self.assertEqual(self.client.get(output("docx")).status_code, 200)
        MarketAccess.objects.filter(pk=self.access.pk).update(markets=["US"])
        self.assertEqual(self.client.get(self.eu_url).status_code, 404)
        self.assertEqual(self.client.get(output("docx")).status_code, 404)
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.assertEqual(self.client.post(detail, {"action": "confirm_impact", "link": link.pk, "reason": "Blocked"}).status_code, 404)
