import os
from datetime import timedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from pms.models import *
class Command(BaseCommand):
    help="역할별 데모 사용자와 비식별 샘플 데이터를 생성합니다."
    def handle(self,*args,**opts):
        password=os.getenv("DEMO_PASSWORD")
        if not password: raise CommandError("DEMO_PASSWORD 환경변수를 설정하세요. 비밀번호는 코드에 저장되지 않습니다.")
        users={}
        for username,role,is_super in [("admin","ADMIN",True),("raqa","RA_QA",False),("staff","STAFF",False)]:
            u,_=User.objects.get_or_create(username=username,defaults={"is_staff":is_super,"is_superuser":is_super,"first_name":{"admin":"관리자","raqa":"RA/QA","staff":"접수 담당"}[username]}); u.set_password(password); u.save(); Profile.objects.update_or_create(user=u,defaults={"role":role}); users[username]=u
        m,_=Manufacturer.objects.get_or_create(name="메디테크 데모",defaults={"country":"대한민국","contact_email":"quality@example.test"})
        d,_=MedicalDevice.objects.get_or_create(manufacturer=m,model_number="MD-100",defaults={"name":"스마트 환자 모니터","risk_class":"II"})
        udi,_=UDI.objects.get_or_create(device=d,device_identifier="(01)08801234567890")
        lot,_=ProductLot.objects.get_or_create(device=d,udi=udi,lot_number="LOT-2026-A",serial_number="",defaults={"manufactured_on":timezone.localdate()-timedelta(days=120),"distributed_quantity":500})
        complaints=[]
        for i in range(5):
            c,_=CustomerComplaint.objects.get_or_create(device=d,udi=udi,lot=lot,title=f"센서 측정 불안정 샘플 {i+1}",defaults={"complaint_type":"SENSOR_ACCURACY","description":"간헐적인 측정값 변동이 보고됨. 데모 데이터입니다.","occurred_on":timezone.localdate()-timedelta(days=i*3),"reported_on":timezone.localdate()-timedelta(days=i*3),"reporter":users["staff"],"assignee":users["raqa"],"due_date":timezone.localdate()+timedelta(days=20-i)})
            complaints.append(c)
        RiskAssessment.objects.update_or_create(complaint=complaints[0],defaults={"severity":5,"probability":4,"rationale":"데모 위험평가","assessed_by":users["raqa"]})
        CAPA.objects.get_or_create(complaint=complaints[0],title="센서 보정 공정 개선",defaults={"corrective_action":"보정 기준 재검증","preventive_action":"출하 검사 샘플 확대","owner":users["raqa"],"due_date":timezone.localdate()+timedelta(days=30)})
        Recall.objects.get_or_create(title="LOT-2026-A 자발적 회수 데모",defaults={"reason":"센서 정확도 조사","risk_level":"HIGH","device":d,"distributed_quantity":500,"target_quantity":200,"recovered_quantity":84,"start_date":timezone.localdate()-timedelta(days=10),"expected_end_date":timezone.localdate()+timedelta(days=35),"owner":users["raqa"],"approval_status":"APPROVED","progress_status":"ACTIVE"})
        RegulatoryReport.objects.get_or_create(document_number="DEMO-RR-2026-001",defaults={"complaint":complaints[0],"required":True,"checklist":{"serious_event":True,"deadline_reviewed":True},"investigation_result":"조사 진행 중","author":users["raqa"],"reviewer":users["admin"]})
        Approval.objects.get_or_create(content_type="CustomerComplaint",object_id=complaints[0].pk,defaults={"requested_by":users["raqa"]})
        self.stdout.write(self.style.SUCCESS("데모 데이터 생성 완료: admin / raqa / staff"))
