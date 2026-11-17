"""Two registered models, fixed synthetic evidence, existing UI actions; no real test results."""
import hashlib
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse
from pms.models import Manufacturer,MedicalDevice,Attachment,ControlledDocument
from pms.dental_models import DentalProject
from pms.mri_registration import ensure_profile
from pms.ra_services import save_record
from pms.services import role


class Command(BaseCommand):
    help="Create two DEMO registered MRI models with distinct coils via the existing Django forms."
    def add_arguments(self,parser):
        parser.add_argument("--user",default="example-hq")
        parser.add_argument("--confirm-example-data",action="store_true")

    def handle(self,*args,**options):
        if not options["confirm_example_data"]:raise CommandError("Use an isolated demo DB and --confirm-example-data")
        user=get_user_model().objects.filter(username=options["user"]).first()
        if not user or role(user) not in ("RA_QA","ADMIN"):raise CommandError("Existing RA account required; seed_market_demo first")
        client=Client();client.force_login(user)
        manufacturer,_=Manufacturer.objects.get_or_create(name="DEMO Registered MRI Manufacturer")
        family=None
        for suffix,coil,software in (("A","DEMO-COIL-A","DEMO-v1"),("B","DEMO-COIL-B","DEMO-v2")):
            model="DEMO-MRI-REGISTERED-"+suffix
            device=MedicalDevice.objects.filter(manufacturer=manufacturer,model_number=model).first()
            if not device:
                data={"manufacturer":manufacturer.pk,"name":"DEMO MRI Registered Family","model_number":model,"product_type":"MRI",
                    "active":"on","configuration_name":"DEMO-config-A","intended_use":"DEMO general diagnostic MRI imaging",
                    "target_population":"DEMO adult population","users":"DEMO imaging professional","environment":"DEMO MRI room",
                    "field_strength_t":"1.5","magnet_type":"DEMO superconducting magnet","rf_coil":coil,"modes":"DEMO-mode",
                    "accessories":"DEMO patient support","software_version":software,"is_example":"on"}
                if family:data["family"]=family.pk
                response=client.post(reverse("market-device-create"),data)
                if response.status_code!=302:raise CommandError(f"Device registration failed {model}: {response.status_code}")
                device=MedicalDevice.objects.get(manufacturer=manufacturer,model_number=model)
            if not family:family=device
            if client.post(reverse("market-mri-start",args=[device.pk])).status_code!=302:raise CommandError("Project start failed")
            project=DentalProject.objects.get(device=device,market="US")
            if project.drafts.exists():
                self.stdout.write(f"{model}: existing /markets/us/devices/{device.pk}/");continue
            spec=project.specification
            text="DEMO SYNTHETIC DATA; INTERNAL WORKFLOW VALIDATION ONLY.\n"+"\n".join(str(spec.get(k,"")) for k in
                ("model","intended_use","target_population","users","environment","field_strength","magnet_type","configuration","coils","modes","accessories","software"))
            text+="\nDEMO labeling and IFU review fixture. No actual clinical or safety conclusion.\n"
            profile=ensure_profile(device,user)
            def document(number,body):
                existing=ControlledDocument.objects.filter(profile=profile,number=number,version=1).first()
                if existing:return existing
                raw=body.encode()
                file=Attachment(ra_profile=profile,uploaded_by=user,scan_status="PASSED",sha256=hashlib.sha256(raw).hexdigest())
                # Only fixed synthetic bytes are fixture-passed; real uploads keep the existing AV path.
                file.file.save(model+"-fixture.txt",ContentFile(raw),save=True)
                return save_record(ControlledDocument(),user,dict(profile=profile,owner=user,title="DEMO synthetic MRI evidence",
                    category="TECHNICAL",number=number,version=1,primary_file=file,change_reason="DEMO",is_example=True),"DEMO")
            base=document("DEMO-MRI-SPEC",text)
            url=reverse("market-writing",args=[device.pk])
            for section in ("MRI.USE","MRI.SPEC","MRI.COIL","MRI.PRED","MRI.LABEL","MRI.SW"):
                r=client.post(url,{"action":"evidence","document":base.pk,"section":section,"page":1,"model":model,
                    "excerpt":text,"evidence_role":"label" if section=="MRI.LABEL" else "specification"})
                if r.status_code!=302:raise CommandError(f"Base evidence failed {section}")
            source_model="DEMO-MRI-REGISTERED-A"
            report=f"DEMO SYNTHETIC TEST ONLY.\n{source_model} DEMO-COIL-A DEMO-v1 DEMO-config-A DEMO-mode DEMO-condition DEMO-method DEMO-threshold DEMO-observation\n"
            report_doc=document("DEMO-MRI-TR",report)
            r=client.post(url,{"action":"evidence","document":report_doc.pk,"section":"MRI.IMG","page":1,"model":source_model,
                "excerpt":report,"evidence_role":"test","coil":"DEMO-COIL-A","software_version":"DEMO-v1","configuration":"DEMO-config-A",
                "mode":"DEMO-mode","conditions":"DEMO-condition","method":"DEMO-method","acceptance":"DEMO-threshold","result":"DEMO-observation"})
            if r.status_code!=302:raise CommandError("Test report fixture failed")
            if suffix=="A":
                predicate={"action":"predicate","k_number":"DEMO-PRED-MRI","confirmed":"on"}
                for key in ("intended_use","field_strength","coils","modes","software"):
                    predicate[key]=spec[key];predicate[key+"_source"]="DEMO synthetic predicate sheet p.1; not an FDA record"
                if client.post(url,predicate).status_code!=302:raise CommandError("Predicate fixture failed")
            for kind in (("description","predicate","performance","labeling","all") if suffix=="A" else ("all",)):
                if client.post(url,{"action":"generate","document_kind":kind}).status_code!=302:raise CommandError("Draft generation failed")
            draft=project.drafts.latest("pk")
            if client.post(reverse("market-dental-output",args=[device.pk,draft.pk,"review"]),{"note":"DEMO internal RA review; no FDA submission"}).status_code!=302:raise CommandError("Review fixture failed")
            self.stdout.write(f"{model}: /markets/us/devices/{device.pk}/ -> {url}; draft {draft.pk}; coil {coil}")
