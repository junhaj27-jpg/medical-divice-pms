"""Create only clearly marked synthetic internal cases; never modify real cohorts."""
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from pms.models import MedicalDevice,Manufacturer,UDI,CustomerComplaint,AdverseEvent
from pms.market_models import ProductMarket,CaseMarket
from pms.market_service import allowed_markets,require_workspace

class Command(BaseCommand):
    help='예시 MRI 기간 비교 자료 생성 (9월 A 2건/AE1건, 10월 B 3건/AE2건)'
    def add_arguments(self,parser):parser.add_argument('--username',default='example-hq')
    @transaction.atomic
    def handle(self,*args,**options):
        user=get_user_model().objects.filter(username=options['username'],is_active=True).first()
        if not user:raise CommandError('기존 활성 RA 계정을 --username으로 지정하세요. seed_market_demo 등의 기존 데모 계정 준비를 먼저 실행하세요.')
        require_workspace(user)
        if 'DE' not in allowed_markets(user):raise CommandError('독일 시장 권한이 있는 RA 계정이 필요합니다.')
        manufacturer,_=Manufacturer.objects.get_or_create(name='DEMO PMS periods manufacturer')
        device,_=MedicalDevice.objects.get_or_create(model_number='DEMO-PMS-PERIOD-MRI',defaults={'name':'예시 MRI 기간 비교 장비','manufacturer':manufacturer,'product_type':'MRI'})
        ProductMarket.objects.get_or_create(device=device,market='DE',defaults={'is_example':True,'owner':user})
        udi,_=UDI.objects.get_or_create(device_identifier='DEMO-PMS-PERIOD-UDI',defaults={'device':device})
        rows=[('A-start','2026-09-01',True),('A-end','2026-09-30',False),('B-start','2026-10-01',True),('B-middle','2026-10-15',False),('B-end','2026-10-31',True)]
        for key,at,adverse in rows:
            case,_=CustomerComplaint.objects.get_or_create(device=device,title='DEMO-PMS-PERIOD-'+key,defaults={'udi':udi,'complaint_type':'DEMO-DEVICE','description':'예시 자료 · 실제 사건 아님','occurred_on':date.fromisoformat(at),'reported_on':date.fromisoformat(at),'reporter':user,'is_example':True})
            CaseMarket.objects.get_or_create(complaint=case,market='DE')
            if adverse:AdverseEvent.objects.get_or_create(complaint=case,defaults={'event_type':'DEMO-EVENT','outcome':'예시','serious':False,'narrative':'예시 자료 · 실제 임상 결과 아님'})
        self.stdout.write(f'예시 제품 #{device.pk} / DE / A 2026-09-01~09-30: 2건(AE1), B 2026-10-01~10-31: 3건(AE2)')
        self.stdout.write(f'/markets/pms-analysis/?device={device.pk}&market=DE&basis=reported_on&a_start=2026-09-01&a_end=2026-09-30&b_start=2026-10-01&b_end=2026-10-31&example=sample&display_timezone=Asia%2FSeoul')
