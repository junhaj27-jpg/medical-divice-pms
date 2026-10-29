"""Explicit synthetic cases only; safe to repeat, never deletes existing rows."""
from datetime import date, timedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pms.models import Manufacturer, MedicalDevice, UDI, ProductLot, CustomerComplaint, Profile, RiskAssessment


class Command(BaseCommand):
    help="테스트용 안전 신호 예시 생성 (실제 법령·운영 성과 아님)"

    def add_arguments(self,parser):
        parser.add_argument("--as-of",default="2026-10-28")
        parser.add_argument("--reporter",required=True,help="예시 사건을 소유할 기존 사용자명")

    @transaction.atomic
    def handle(self,*args,**options):
        try: end=date.fromisoformat(options["as_of"])
        except ValueError: raise CommandError("YYYY-MM-DD 기준일을 입력하세요.")
        user=User.objects.filter(username=options["reporter"]).first()
        if not user: raise CommandError("기존 사용자명을 지정하세요. 계정은 자동 생성하지 않습니다.")
        m,_=Manufacturer.objects.get_or_create(name="TEST ONLY 안전 신호 예시 제조사")
        d,_=MedicalDevice.objects.get_or_create(manufacturer=m,model_number="TEST-SAFETY-ONLY",defaults={"name":"TEST ONLY 안전 신호 예시 기기"})
        u,_=UDI.objects.get_or_create(device_identifier="TEST-SAFETY-ONLY",defaults={"device":d})
        created=0
        for lotname,offsets in (("TEST-NORMAL",[35,7]),("TEST-REPEAT",[10,8,6]),("TEST-NEW",[3,2,1])):
            lot,_=ProductLot.objects.get_or_create(device=d,udi=u,lot_number=lotname,defaults={"distributed_quantity":0})
            for offset in offsets:
                day=end-timedelta(days=offset)
                title=f"TEST ONLY {end} {lotname} D-{offset}"
                _,fresh=CustomerComplaint.objects.get_or_create(reporter=user,title=title,is_example=True,defaults=dict(device=d,udi=u,lot=lot,complaint_type="TEST-SAFETY",description="합성 테스트 자료. 실제 운영 성과·환자정보가 아닙니다.",occurred_on=day,reported_on=day))
                created+=int(fresh)
        self.stdout.write(f"테스트용 사건 {created}건 추가. /safety/ 에서 대상=테스트용 사건, {end-timedelta(days=27)} ~ {end}. 기간별 분모 없음.")
