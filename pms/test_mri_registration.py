from copy import deepcopy
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import shutil
from unittest.mock import patch
from types import SimpleNamespace
from zipfile import ZipFile
import hashlib

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from .test_dental import DentalTests
from .models import MedicalDevice, Attachment, ControlledDocument
from .mri_models import MRIConfiguration
from .market_models import MarketAccess, ProductMarket
from .dental_models import DentalProject, WritingTemplate
from .dental_views import documents_for, references_for
from .dental_workflow import build_snapshot, stale_sections
from .mri_registration import ensure_profile
from .ra_services import save_record


class MRIRegistrationTests(DentalTests):
    def setUp(self):
        super().setUp()
        folder=Path.cwd()/f"mri_registration_test_{uuid4().hex}"
        folder.mkdir()
        def cleanup():
            if folder.resolve().parent != Path.cwd().resolve():raise RuntimeError("Unexpected fixture cleanup path")
            shutil.rmtree(folder)
        self.addCleanup(cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=Path(folder)))
        self.data={"manufacturer":self.device.manufacturer_id,"name":"DEMO Registered MRI","model_number":"DEMO-MRI-REG-A",
            "product_type":"MRI","active":"on","configuration_name":"DEMO-config-A","intended_use":"DEMO general MRI imaging",
            "target_population":"DEMO adults","users":"DEMO operator","environment":"DEMO room",
            "field_strength_t":"1.5","magnet_type":"DEMO magnet","rf_coil":"DEMO-COIL-A","modes":"DEMO-mode",
            "accessories":"DEMO support","software_version":"DEMO-v1","is_example":"on"}

    def register(self,**changes):
        data={**self.data,**changes}
        response=self.client.post(reverse("market-device-create"),data)
        self.assertEqual(response.status_code,302,response.content[:200])
        return MedicalDevice.objects.get(model_number=data["model_number"])

    def start(self,device):
        url=reverse("market-mri-start",args=[device.pk])
        self.assertEqual(self.client.post(url).status_code,302)
        return DentalProject.objects.get(device=device,market="US")

    def proof(self,project,source_model=None,coil=None,software=None,version=1,previous=None):
        spec=project.specification
        model=source_model or spec["model"]; coil=coil or spec["coils"]; software=software or spec["software"]
        text=" ".join(str(spec.get(k,"")) for k in ("intended_use","target_population","users","environment","field_strength","magnet_type","configuration","modes","accessories"))
        excerpt=f"{model} {coil} {software}. DEMO observation only; no actual test pass claim."
        raw=("DEMO SYNTHETIC EVIDENCE\n"+text+"\n"+excerpt+"\nDEMO-method DEMO-threshold DEMO-result DEMO-condition DEMO-mode").encode()
        profile=ensure_profile(project.device,self.user)
        file=Attachment(ra_profile=profile,uploaded_by=self.user,scan_status="PASSED",sha256=hashlib.sha256(raw).hexdigest())
        file.file.save("synthetic.txt",ContentFile(raw),save=True)
        document=save_record(ControlledDocument(),self.user,dict(profile=profile,owner=self.user,title="DEMO specification/test",
            category="TECHNICAL",number="DEMO-MRI-TR",version=version,primary_file=file,supersedes=previous,change_reason="DEMO",is_example=True),"DEMO")
        return document,raw.decode(),excerpt

    def connect(self,project,document,text,section="MRI.SPEC",**values):
        payload={"action":"evidence","document":document.pk,"section":section,"page":1,"excerpt":text,
            "model":project.specification["model"],"evidence_role":"specification",**values}
        return self.client.post(reverse("market-writing",args=[project.device_id]),payload)

    def test_registered_model_starts_project_without_reentry_and_exports_all_documents(self):
        self.assertContains(self.client.get(reverse("market-device-create")),"MRI 촬영 장비")
        device=self.register();config=device.mri_configurations.get()
        self.assertEqual(str(config.field_strength_t),"1.500")
        self.assertContains(self.client.get(reverse("market-device-detail",args=[device.pk])),"미국 인허가 문서 작성")
        project=self.start(device);self.start(device)
        self.assertEqual(DentalProject.objects.filter(device=device).count(),1)
        self.assertEqual(project.template.version,2)
        self.assertEqual(project.specification["coils"],"DEMO-COIL-A")
        self.assertEqual(project.specification["product_code"],"")
        self.assertFalse(project.specification["scope_confirmed"])
        self.assertTrue(project.fda_references.filter(source__key="mri-lnh").exists())
        doc,text,_=self.proof(project)
        for section in ("MRI.USE","MRI.SPEC","MRI.COIL","MRI.LABEL"):
            self.assertEqual(self.connect(project,doc,text,section).status_code,302)
        url=reverse("market-writing",args=[device.pk])
        self.assertEqual(self.client.post(url,{"action":"generate"}).status_code,302)
        draft=project.drafts.get();snapshot=deepcopy(draft.snapshot)
        output=lambda kind:reverse("market-dental-output",args=[device.pk,draft.pk,kind])
        self.assertEqual(snapshot["estar"]["version"],"nIVD 7.1")
        self.assertEqual(snapshot["estar"]["checked_on"],"2026-11-16")
        with ZipFile(BytesIO(b"".join(self.client.get(output("bundle")).streaming_content))) as bundle:
            self.assertEqual(set(bundle.namelist()),{"description.docx","predicate.docx","performance.docx","labeling.docx","matrix.csv","gaps.csv","mapping.csv"})
            xml=ZipFile(BytesIO(bundle.read("description.docx"))).read("word/document.xml").decode()
            for value in ("Draft for RA Review","DEMO","FDA review basis:","Product evidence:","DEMO-COIL-A"):self.assertIn(value,xml)
            self.assertIn("<w:tbl>",xml)
            self.assertIn("MRI.IMG",bundle.read("gaps.csv").decode("utf-8-sig"))
        for kind in ("description","predicate","performance","labeling"):
            self.assertEqual(self.client.post(url,{"action":"generate","document_kind":kind}).status_code,302)
            part=project.drafts.latest("pk").snapshot
            self.assertEqual(part["document_kind"],kind)
            self.assertTrue(part["rows"])
        self.assertEqual(self.client.post(output("review"),{"note":"DEMO RA review"}).status_code,302)
        draft.refresh_from_db();self.assertEqual(draft.snapshot,snapshot)
        self.assertEqual(ProductMarket.objects.get(device=device,market="US").status,"UNKNOWN")
        project.refresh_from_db()
        manual=deepcopy(project.specification);manual.pop("registered_configuration")
        project.specification=manual;project.save(update_fields=["specification"])
        self.start(device);project.refresh_from_db()
        self.assertEqual(project.specification["registered_configuration"]["id"],config.pk)
        self.assertEqual(project.specification["previous_project_inputs"]["model"],device.model_number)

    def test_coil_model_software_mismatch_blocked_until_ra_applicability_review(self):
        first=self.register();a=self.start(first)
        second=self.register(model_number="DEMO-MRI-REG-B",rf_coil="DEMO-COIL-B",software_version="DEMO-v2",family=first.pk)
        b=self.start(second)
        self.assertEqual(second.mri_configurations.get().family_id,first.pk)
        doc,_,excerpt=self.proof(b,source_model=first.model_number,coil="DEMO-COIL-A",software="DEMO-v1")
        result=self.connect(b,doc,excerpt,"MRI.IMG",model=first.model_number,coil="DEMO-COIL-A",software_version="DEMO-v1",
            evidence_role="test",configuration="DEMO-config-A",mode="DEMO-mode",conditions="DEMO-condition",method="DEMO-method",acceptance="DEMO-threshold",result="DEMO-result")
        self.assertEqual(result.status_code,302)
        row=next(r for r in build_snapshot(b,references_for(b,documents_for(second)))["rows"] if r["section"]=="MRI.IMG")
        for word in ("모델 불일치","RF 코일 불일치","소프트웨어 버전 불일치"):self.assertTrue(any(word in g for g in row["gaps"]))
        self.assertFalse(row["selected"])
        url=reverse("market-writing",args=[second.pk]);self.client.post(url,{"action":"generate","document_kind":"performance"})
        old=b.drafts.get();before=deepcopy(old.snapshot)
        output=reverse("market-dental-output",args=[second.pk,old.pk,"docx"])
        xml=ZipFile(BytesIO(b"".join(self.client.get(output).streaming_content))).read("word/document.xml").decode()
        self.assertNotIn("Product evidence: "+excerpt,xml)
        evidence=b.evidence.get()
        payload={"action":"review_mri_evidence","evidence_id":evidence.pk,"previous":0,"decision":"accept","rationale":"DEMO engineering justification; synthetic fixtures only"}
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(self.client.post(url,payload).status_code,400)
        row=next(r for r in build_snapshot(b,references_for(b,documents_for(second)))["rows"] if r["section"]=="MRI.IMG")
        self.assertTrue(row["selected"])
        old.refresh_from_db();self.assertEqual(old.snapshot,before)
        foreign,_,_=self.proof(a)
        self.assertEqual(self.connect(b,foreign,excerpt).status_code,400)

    def test_configuration_revision_preserves_old_draft_and_requires_explicit_sync(self):
        device=self.register();project=self.start(device);url=reverse("market-writing",args=[device.pk])
        self.client.post(url,{"action":"generate"});draft=project.drafts.get();before=deepcopy(draft.snapshot)
        config=device.mri_configurations.first()
        edit=reverse("market-device-edit",args=[device.pk])
        data={**self.data,"configuration_revision":config.pk,"rf_coil":"DEMO-COIL-C"}
        self.assertEqual(self.client.post(edit,data).status_code,302)
        self.assertEqual(device.mri_configurations.count(),2)
        self.assertEqual(self.client.post(edit,data).status_code,200) # conflict shown in form; no overwrite
        self.assertTrue(stale_sections(project,before,documents_for(device)))
        self.assertEqual(self.client.post(url,{"action":"generate"}).status_code,400)
        self.assertEqual(self.client.post(url,{"action":"sync_product"}).status_code,302)
        project.refresh_from_db();self.assertEqual(project.specification["coils"],"DEMO-COIL-C")
        self.assertFalse(project.specification["scope_confirmed"])
        draft.refresh_from_db();self.assertEqual(draft.snapshot,before)
        self.assertEqual(self.client.get(reverse("market-dental-output",args=[device.pk,draft.pk,"docx"])).status_code,200)

    def test_document_revision_and_upload_scanner_failure(self):
        device=self.register();project=self.start(device);doc,text,_=self.proof(project)
        self.connect(project,doc,text);url=reverse("market-writing",args=[device.pk]);self.client.post(url,{"action":"generate"})
        draft=project.drafts.get();before=deepcopy(draft.snapshot)
        self.proof(project,version=2,previous=doc)
        self.assertIn("MRI.SPEC",stale_sections(project,before,documents_for(device)))
        draft.refresh_from_db();self.assertEqual(draft.snapshot,before)
        with override_settings(ANTIVIRUS_COMMAND=[]):
            response=self.client.post(reverse("market-mri-upload",args=[device.pk]),{"number":"DEMO-UP","version":1,"title":"DEMO upload",
                "document_kind":"Test report","file":SimpleUploadedFile("demo.txt",b"DEMO fixture")})
        self.assertEqual(response.status_code,400)
        self.assertFalse(ControlledDocument.objects.filter(number="DEMO-UP").exists())
        with override_settings(ANTIVIRUS_COMMAND=["DEMO-scanner"]),patch("pms.file_security.subprocess.run",return_value=SimpleNamespace(returncode=0)):
            response=self.client.post(reverse("market-mri-upload",args=[device.pk]),{"number":"DEMO-UP","version":1,"title":"DEMO upload",
                "document_kind":"Test report","file":SimpleUploadedFile("demo.txt",b"DEMO fixture")})
        self.assertEqual(response.status_code,302)
        self.assertEqual(ControlledDocument.objects.get(number="DEMO-UP").primary_file.scan_status,"PASSED")

    def test_revoked_permission_and_invalid_registration(self):
        self.assertContains(self.client.post(reverse("market-device-create"),{**self.data,"field_strength_t":"-1"}),"0.001")
        device=self.register();project=self.start(device);url=reverse("market-writing",args=[device.pk])
        from .models import CustomerComplaint,UDI
        from .market_models import CaseMarket
        from datetime import date
        udi=UDI.objects.create(device=device,device_identifier="DEMO-REG-UDI")
        case=CustomerComplaint.objects.create(device=device,udi=udi,complaint_type="DEMO",title="DEMO country isolation",description="DEMO",occurred_on=date(2026,11,16),reporter=self.user,is_example=True)
        CaseMarket.objects.create(complaint=case,market="DE")
        self.assertEqual(self.client.get(reverse("market-device-detail",args=[device.pk])).context["complaint_count"],0)
        self.client.post(url,{"action":"generate"});draft=project.drafts.get()
        MarketAccess.objects.filter(pk=self.access.pk).update(markets=["DE"])
        for name,args in (("market-device-detail",[device.pk]),("market-mri-start",[device.pk]),("market-mri-upload",[device.pk]),
                          ("market-dental-output",[device.pk,draft.pk,"bundle"])):
            response=self.client.post(reverse(name,args=args)) if name=="market-mri-start" else self.client.get(reverse(name,args=args))
            self.assertIn(response.status_code,(403,404))
