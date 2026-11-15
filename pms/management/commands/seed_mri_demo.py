"""Synthetic files and device records only; explicit local-demo opt-in required."""
import hashlib
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import Client
from django.urls import reverse
from pms.dental_models import DentalProject, WritingTemplate
from pms.fda_library_models import FDAReferenceVersion
from pms.market_models import ProductMarket
from pms.models import Manufacturer, MedicalDevice, BusinessPartner, RegulatoryProfile, ControlledDocument, Attachment
from pms.ra_services import save_record
from pms.services import role


class Command(BaseCommand):
    help = "Create three DEMO MRI/MR writing projects via the existing forms, in an explicitly selected local demo DB."

    def add_arguments(self, parser):
        parser.add_argument("--user", default="example-hq")
        parser.add_argument("--confirm-example-data", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm_example_data"]:
            raise CommandError("Use --confirm-example-data with an isolated local demo DB.")
        user = get_user_model().objects.filter(username=options["user"]).first()
        if not user or role(user) not in ("RA_QA", "ADMIN"):
            raise CommandError("An existing RA account is required (seed_market_demo first).")
        client = Client(); client.force_login(user)
        maker, _ = Manufacturer.objects.get_or_create(name="DEMO MRI Workflow Manufacturer")
        organization, _ = BusinessPartner.objects.get_or_create(name="DEMO MRI Research Organization")
        examples = [
            ("mri-equipment", "DEMO-MRI-01", "DEMO MRI scanner", "General MRI workflow validation only",
             "DEMO-MRI-01 is a synthetic MRI scanner example with a demonstration 1.5 T field strength; no test pass claim."),
            ("mri-software", "DEMO-ROI-01", "DEMO NeuroAge-MAS ROI research analysis", "Research analysis of ROI volume tables derived from MRI; no clinical diagnosis",
             "DEMO-ROI-01 NeuroAge-MAS example consumes derived ROI volume tables in CSV format, not original MRI images. Outputs are research-only; no clinical diagnostic claim."),
            ("mr-environment", "DEMO-MR-ENV-01", "DEMO MR environment device", "Synthetic device used to review MR conditions",
             "DEMO-MR-ENV-01 is a synthetic MR environment device. Test conditions DEMO-condition-A differ from label conditions DEMO-condition-B; RA review is required."),
        ]
        for key, model, name, intended, excerpt in examples:
            device, _ = MedicalDevice.objects.get_or_create(manufacturer=maker,model_number=model,defaults={"name":name})
            ProductMarket.objects.get_or_create(device=device,market="US",defaults={"is_example":True,"owner":user})
            url = reverse("market-writing",args=[device.pk])
            if DentalProject.objects.filter(device=device,market="US").exists():
                self.stdout.write(f"{model}: existing {url}"); continue
            template=WritingTemplate.objects.get(key=key,version=1)
            payload={"action":"project","template_id":template.pk,"product_name":name,"model":model,"intended_use":intended,
                "users":"Research RA staff","environment":"DEMO research laboratory","product_version":"DEMO-v1","example":"on",
                "product_code":"LNH" if key=="mri-equipment" else "","regulation":"892.1000" if key=="mri-equipment" else "",
                "scope_confirmed":"on" if key=="mri-equipment" else "","confirmed_pathway":"DEMO RA-reviewed 510(k) candidate" if key=="mri-equipment" else "",
                "field_strength":"1.5 T (DEMO)","coils":"DEMO coil","modes":"DEMO mode","configuration":"DEMO-config-A",
                "clinical_claim":"Research only; no clinical diagnosis","inputs":"Derived ROI volume table","outputs":"Research-only analysis",
                "raw_mri_processing":"No; derived CSV table only","formats":"CSV","software":"DEMO-v1","algorithm_version":"DEMO-model-v1",
                "device_type":"DEMO device","use_conditions":"DEMO-condition-A","label_conditions":"DEMO-condition-B"}
            response=client.post(url,payload)
            if response.status_code!=302: raise CommandError(f"Project form failed: {model} {response.status_code}")
            project=DentalProject.objects.get(device=device,market="US")
            profile=save_record(RegulatoryProfile(),user,dict(device=device,jurisdiction="US",organization=organization,
                organization_role="MANUFACTURER",title=name,owner=user,is_example=True),"DEMO fixture")
            text=("DEMO — SYNTHETIC FIXTURE, NOT A REAL TEST REPORT.\n"+excerpt+"\n"+
                  f"{model} DEMO-v1 DEMO-config-A DEMO-mode DEMO-condition-A DEMO-condition-B DEMO-method DEMO-threshold DEMO-observation\n").encode()
            file=Attachment(ra_profile=profile,uploaded_by=user,scan_status="PASSED",sha256=hashlib.sha256(text).hexdigest())
            # Only fixed synthetic fixture bytes are marked passed; real uploads retain the existing scanner workflow.
            file.file.save(model+"-synthetic.txt",ContentFile(text),save=True)
            document=save_record(ControlledDocument(),user,dict(profile=profile,title=name+" synthetic evidence",owner=user,is_example=True,
                category="TECHNICAL",number=model+"-SPEC",version=1,primary_file=file,change_reason="DEMO fixture"),"DEMO fixture")
            for item in template.items:
                source=FDAReferenceVersion.objects.get(key=item["source_key"],version=1)
                r=client.post(url,{"action":"fda_source","source_id":source.pk,"section":item["id"],"clause":item["source_section"],
                    "page":item["page"],"rationale":"DEMO applicability review; not an actual submission determination"})
                if r.status_code!=302: raise CommandError("Source link failed")
            r=client.post(url,{"action":"evidence","document":document.pk,"section":template.items[0]["id"],"page":1,
                "model":model,"excerpt":excerpt,"evidence_role":"specification"})
            if r.status_code!=302: raise CommandError("Evidence form failed")
            if key=="mr-environment":
                for evidence_role,conditions in (("test","DEMO-condition-A"),("label","DEMO-condition-B")):
                    r=client.post(url,{"action":"evidence","document":document.pk,"section":"MR.LABEL","page":1,
                        "model":model,"excerpt":excerpt,"evidence_role":evidence_role,"configuration":"DEMO-config-A",
                        "conditions":conditions,"mode":"DEMO-mode","method":"DEMO-method","acceptance":"DEMO-threshold","result":"DEMO-observation"})
                    if r.status_code!=302: raise CommandError("MR label comparison fixture failed")
            if client.post(url,{"action":"generate"}).status_code!=302: raise CommandError("Draft generation failed")
            self.stdout.write(f"{model}: {url} draft {project.drafts.latest('pk').pk}")
