"""Local example links only. Does not apply a product change or invent regulatory decisions."""
import json
from copy import deepcopy
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from pms.models import MedicalDevice,Attachment,ControlledDocument
from pms.market_models import ProductMarket
from pms.dental_models import DentalProject,WritingTemplate
from pms.dental_views import documents_for,references_for
from pms.dental_workflow import build_snapshot
from pms.market_service import require_workspace,allowed_markets
from pms.review_tasks import ensure_profile,lock
from pms.ra_services import save_record
from pms.file_security import safe_attachment_bytes
from pms.services import audit

class Command(BaseCommand):
    help='Prepare US/DE market links and known scanned example evidence for an existing DEMO MRI.'
    def add_arguments(self,parser):
        parser.add_argument('--user',required=True)
        parser.add_argument('--model',default='DEMO-MRI-REGISTERED-A')
        parser.add_argument('--confirm-example-data',action='store_true')
    @transaction.atomic
    def handle(self,**options):
        if not options['confirm_example_data']:raise CommandError('--confirm-example-data is required')
        user=get_user_model().objects.get(username=options['user']);require_workspace(user)
        if not {'US','DE'}<=set(allowed_markets(user)):raise CommandError('US and DE grants required')
        device=MedicalDevice.objects.get(model_number=options['model'],product_type='MRI');lock(MedicalDevice,device.pk)
        config=device.mri_configurations.first()
        if not device.model_number.startswith('DEMO-') or not config or not config.is_example:raise CommandError('Existing example MRI required; run seed_registered_mri_demo first')
        us=DentalProject.objects.get(device=device,market='US')
        source=Attachment.objects.filter(ra_profile__device=device,ra_profile__jurisdiction='US',scan_status='PASSED').first()
        if not source:raise CommandError('Existing scanned DEMO US proof required')
        data=safe_attachment_bytes(source)
        if b'DEMO' not in data.upper():raise CommandError('Known example bytes required')
        registration,created=ProductMarket.objects.get_or_create(device=device,market='DE',defaults={'is_example':True,'rationale':'DEMO EU/DE market linkage for internal impact review; registration status remains UNKNOWN.'})
        profile=ensure_profile(user,device,'EU')
        # Same bytes and hash as an already scanned DEMO file; no new upload or scanner bypass endpoint.
        proof=Attachment.objects.filter(ra_profile=profile,sha256=source.sha256,original_name='DEMO-shared-scanned-evidence.txt').first()
        if not proof:
            proof=Attachment.objects.create(ra_profile=profile,file=source.file.name,original_name='DEMO-shared-scanned-evidence.txt',uploaded_by=user,scan_status=source.scan_status,sha256=source.sha256,detected_type=source.detected_type,scanned_at=source.scanned_at)
            audit(user,'DEMO_PROOF_REFERENCE',proof,after={'original_attachment_id':source.pk,'sha256':source.sha256})
        document=ControlledDocument.objects.filter(profile=profile,number='DEMO-MRI-CHANGE-PROOF',version=1).first()
        if not document:document=save_record(ControlledDocument(),user,{'profile':profile,'owner':user,'is_example':profile.is_example,'title':'DEMO MRI evidence for product-change review','category':'TECHNICAL','number':'DEMO-MRI-CHANGE-PROOF','version':1,'primary_file':proof,'change_reason':'DEMO reference to existing scanned same-product example bytes'},'DEMO existing scanned file reference')
        template=WritingTemplate.objects.filter(key='eu-mdr',state='PUBLISHED').order_by('-version').first()
        if not template:raise CommandError('Published EU collection template required')
        spec=deepcopy(us.specification);spec.update(product_code='',regulation='',confirmed_pathway='',scope_confirmed=False)
        eu,_=DentalProject.objects.get_or_create(device=device,market='EU',defaults={'owner':user,'template':template,'guide':us.guide,'specification':spec})
        if not eu.drafts.exists():eu.drafts.create(author=user,snapshot=build_snapshot(eu,references_for(eu,documents_for(device,'EU')),use_ai=False))
        self.stdout.write(json.dumps({'device_id':device.pk,'model':device.model_number,'software':config.software_version,'us_proof':source.pk,'eu_proof':proof.pk,'eu_project':eu.pk,'de_market_added':created,'registration_status':registration.status,'note':'Example links only; product configuration unchanged; no real antivirus execution'},ensure_ascii=False))
