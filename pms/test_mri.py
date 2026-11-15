from copy import deepcopy
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from django.urls import reverse
from .dental_models import DentalProject, WritingTemplate
from .dental_workflow import build_snapshot, ready, stale_sections
from .dental_views import documents_for, references_for
from .fda_library import record_reference
from .fda_library_models import FDAReferenceVersion, ProjectFDAReference
from .market_models import MarketAccess, ProductMarket
from .mri_catalog import catalog
from .test_dental import DentalTests


class MRITests(DentalTests):
    def create_project(self, key, confirmed=True):
        self.template = WritingTemplate.objects.get(key=key)
        self.workspace = reverse("market-writing", args=[self.device.pk])
        payload = {**self.spec, "template_id":self.template.pk,"users":"Research staff","environment":"Research laboratory",
            "product_version":"DEMO-v1", "product_code":"LNH" if key == "mri-equipment" else "",
            "regulation":"892.1000" if key == "mri-equipment" else "",
            "scope_confirmed":"on" if confirmed else "", "confirmed_pathway":"RA-confirmed DEMO pathway" if confirmed else "",
            "clinical_claim":"Research only; no diagnostic claim", "inputs":"Derived ROI volume table", "outputs":"Research analysis",
            "raw_mri_processing":"No", "formats":"CSV", "software":"DEMO-v1", "configuration":"High"}
        self.assertEqual(self.client.post(self.workspace,payload).status_code,302)
        return DentalProject.objects.get(device=self.device,market="US")

    def link_all(self, project):
        for item in project.template.items:
            source=FDAReferenceVersion.objects.get(key=item["source_key"],version=1)
            payload={"action":"fda_source","section":item["id"],"source_id":source.pk,
                     "clause":item["source_section"],"page":item["page"],"rationale":"DEMO RA applicability review"}
            self.assertEqual(self.client.post(self.workspace,payload).status_code,302)

    def add_evidence(self, project, section=None, **extra):
        doc=self.document()
        payload={"action":"evidence","section":section or project.template.items[0]["id"],"document":doc.pk,
                 "page":1,"model":"DEMO-01","excerpt":"Optical test data.","evidence_role":"specification",**extra}
        self.assertEqual(self.client.post(self.workspace,payload).status_code,302)
        return doc

    def test_library_catalog_search_duplicate_and_revision_immutability(self):
        url=reverse("market-fda-library")
        self.assertContains(self.client.get(reverse("market-dashboard")),url)
        self.assertContains(self.client.get(url+"?q=MRI%2FMR&device_type=mr-environment"),"Testing and Labeling")
        self.assertNotContains(self.client.get(url+"?device_type=mr-environment"),"Nuclear magnetic resonance imaging system")
        self.assertContains(self.client.get(url+"?q=induced"),"Testing and Labeling")
        for values in catalog():
            source,created=record_reference(values)
            self.assertFalse(created)
            self.assertEqual(source.version,1)
        self.assertEqual(FDAReferenceVersion.objects.count(),5)
        source=FDAReferenceVersion.objects.get(key="mrdd")
        self.assertEqual(len(source.pages),21)
        self.assertEqual(len(FDAReferenceVersion.objects.get(key="mr-environment").pages),32)
        self.assertIn("404",source.failure_reason)
        self.assertEqual(source.revised_on.isoformat(),"2023-10-10")
        detail=reverse("market-fda-source",args=[source.pk])
        self.assertContains(self.client.get(detail),"Direct PDF fetch")
        self.assertContains(self.client.get(detail),"2023-10-10")
        payload={"key":"mri-iec-60601-2-33","title":"DEMO revised standard check","source_type":"standard",
            "document_version":"DEMO review snapshot","checked_on":"2026-11-15","official_url":"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/search.cfm",
            "scope":"DEMO limitations","device_types":["mri-equipment"],"section":"DEMO record","page":0,
            "standard_number":"IEC 60601-2-33","edition":"RA 확인 필요","recognition_scope":"RA 확인 필요"}
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(FDAReferenceVersion.objects.filter(key=payload["key"]).count(),2)
        self.assertEqual(list(self.client.get(url+"?q=THIS-DOES-NOT-EXIST").context["sources"]), [])

    def test_equipment_export_and_source_revision_preserves_old_citations(self):
        project=self.create_project("mri-equipment")
        self.link_all(project)
        count=project.fda_references.count()
        self.link_all(project)
        self.assertEqual(project.fda_references.count(),count)
        doc=self.add_evidence(project)
        registration=ProductMarket.objects.get(device=self.device,market="US")
        before=(registration.status,registration.classification,registration.pathway)
        self.assertEqual(self.client.post(self.workspace,{"action":"generate"}).status_code,302)
        draft=project.drafts.get(); original=deepcopy(draft.snapshot)
        source=FDAReferenceVersion.objects.get(key="mrdd")
        self.assertEqual(original["rows"][0]["fda_references"][0]["source_id"],source.pk)
        output=lambda k:reverse("market-dental-output",args=[self.device.pk,draft.pk,k])
        xml=ZipFile(BytesIO(b"".join(self.client.get(output("docx")).streaming_content))).read("word/document.xml").decode()
        for value in ("FDA review basis:","Product evidence:","Optical test data.","Final — 2023-10-10","Draft for RA Review"):
            self.assertIn(value,xml)
        text=b"".join(self.client.get(output("matrix")).streaming_content).decode("utf-8-sig")
        self.assertIn("FDA 근거:",text);self.assertIn("제품 증빙:",text)
        values=next(x for x in catalog() if x["key"]=="mrdd")
        revision,_=record_reference({**values,"scope":values["scope"]+" DEMO revision"},self.user)
        draft.refresh_from_db();self.assertEqual(draft.snapshot,original)
        self.assertIn("MRI.USE",stale_sections(project,original,documents_for(self.device)))
        self.assertContains(self.client.get(self.workspace),"재검토 필요")
        self.assertEqual(self.client.get(output("docx")).status_code,200)
        first=project.template.items[0]
        self.assertEqual(self.client.post(self.workspace,{"action":"fda_source","section":first["id"],"source_id":revision.pk,
            "clause":first["source_section"],"page":first["page"],"rationale":"DEMO explicit version switch"}).status_code,302)
        current=build_snapshot(project,references_for(project,documents_for(self.device)))["rows"][0]
        self.assertEqual(current["fda_references"][0]["source_id"],revision.pk)
        self.assertFalse(any("FDA 출처 개정" in gap for gap in current["gaps"]))
        registration.refresh_from_db()
        self.assertEqual((registration.status,registration.classification,registration.pathway),before)
        self.client.post(reverse("market-language"),{"language":"de-DE","next":self.workspace})
        draft.refresh_from_db();self.assertEqual(draft.snapshot,original)

    def test_software_research_collection_does_not_inherit_scanner_classification(self):
        project=self.create_project("mri-software",confirmed=False)
        self.assertEqual(project.specification["product_code"],"")
        self.assertEqual(project.specification["regulation"],"")
        self.link_all(project);self.add_evidence(project)
        self.assertTrue(ready(project))
        self.client.post(self.workspace,{"action":"generate"})
        draft=project.drafts.get()
        self.assertFalse(draft.snapshot["submission_mapping_ready"])
        self.assertTrue(all("보류" in row["mapping"] for row in draft.snapshot["rows"]))
        self.assertEqual({r["section"] for r in draft.snapshot["rows"]},{i["id"] for i in self.template.items})
        self.assertContains(self.client.get(self.workspace),"원본 MRI 처리")
        # No LNH lookup is triggered just because the project uses MRI-derived data.
        with patch("pms.dental_views.case_results",return_value=[]) as lookup:
            self.client.get(self.workspace);lookup.assert_not_called()
            self.client.get(self.workspace+"?k_number=K123456")
            lookup.assert_called_once_with("k_number","K123456")

    def test_mr_environment_test_label_conditions_and_model_mismatch(self):
        project=self.create_project("mr-environment")
        self.link_all(project)
        doc=self.add_evidence(project,"MR.LABEL",evidence_role="test",conditions="bench",configuration="High")
        self.client.post(self.workspace,{"action":"evidence","section":"MR.LABEL","document":doc.pk,"page":1,
            "model":"DEMO-02","excerpt":"Optical test data.","evidence_role":"label","conditions":"room","configuration":"High"})
        rows=build_snapshot(project,references_for(project,documents_for(self.device)))["rows"]
        label=next(r for r in rows if r["section"]=="MR.LABEL")
        self.assertTrue(any("조건 또는 구성 불일치" in gap for gap in label["gaps"]))
        self.assertTrue(any("모델 불일치" in gap for gap in label["gaps"]))
        self.assertFalse(label["selected"])
        self.assertTrue(any("시험 모델" in gap for r in rows if r["section"]=="MR.HEAT" for gap in r["gaps"]))

    def test_permission_and_invalid_source_citation(self):
        project=self.create_project("mri-equipment")
        source=FDAReferenceVersion.objects.get(key="mrdd")
        payload={"action":"fda_source","section":"MRI.USE","source_id":source.pk,"clause":"Nonexistent provision",
                 "page":999,"rationale":"DEMO"}
        self.assertEqual(self.client.post(self.workspace,payload).status_code,400)
        self.assertFalse(ProjectFDAReference.objects.exists())
        self.link_all(project);self.add_evidence(project);self.client.post(self.workspace,{"action":"generate"})
        draft=project.drafts.get()
        MarketAccess.objects.filter(pk=self.access.pk).update(markets=["DE"])
        for url in (self.workspace,reverse("market-fda-library"),reverse("market-fda-source",args=[source.pk]),
                    reverse("market-dental-output",args=[self.device.pk,draft.pk,"docx"])):
            self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.post(self.workspace,payload).status_code,404)

    def test_switch_from_equipment_to_software_clears_candidate_classification(self):
        project=self.create_project("mri-equipment")
        self.assertEqual(project.specification["product_code"],"LNH")
        software=WritingTemplate.objects.get(key="mri-software")
        self.assertEqual(self.client.post(self.workspace,{"action":"template","template_id":software.pk}).status_code,302)
        project.refresh_from_db()
        self.assertEqual(project.specification["product_code"],"")
        self.assertEqual(project.specification["regulation"],"")
        self.assertEqual(project.specification["confirmed_pathway"],"")
        self.assertEqual(project.specification["previous_classification_input"]["product_code"],"LNH")
        self.assertFalse(project.specification["scope_confirmed"])
