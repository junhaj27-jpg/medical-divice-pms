import os
from datetime import timedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from pms.services import decide_approval, request_complaint_approval, transition_complaint
from pms.workflow import close_capa, evaluate_capa
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
            c,_=CustomerComplaint.objects.get_or_create(device=d,udi=udi,lot=lot,title=f"센서 측정 불안정 샘플 {i+1}",defaults={"is_example":True,"complaint_type":"SENSOR_ACCURACY","description":"간헐적인 측정값 변동이 보고됨. 데모 데이터입니다.","occurred_on":timezone.localdate()-timedelta(days=i*3),"reported_on":timezone.localdate()-timedelta(days=i*3),"reporter":users["staff"],"assignee":users["raqa"],"due_date":timezone.localdate()+timedelta(days=20-i)})
            complaints.append(c)
        RiskAssessment.objects.update_or_create(complaint=complaints[0],defaults={"severity":5,"probability":4,"rationale":"데모 위험평가","assessed_by":users["raqa"]})
        CAPA.objects.get_or_create(complaint=complaints[0],title="센서 보정 공정 개선",defaults={"corrective_action":"보정 기준 재검증","preventive_action":"출하 검사 샘플 확대","owner":users["raqa"],"due_date":timezone.localdate()+timedelta(days=30)})
        Recall.objects.get_or_create(title="LOT-2026-A 자발적 회수 데모",defaults={"reason":"센서 정확도 조사","risk_level":"HIGH","device":d,"distributed_quantity":500,"target_quantity":200,"recovered_quantity":84,"start_date":timezone.localdate()-timedelta(days=10),"expected_end_date":timezone.localdate()+timedelta(days=35),"owner":users["raqa"],"approval_status":"APPROVED","progress_status":"ACTIVE"})
        RegulatoryReport.objects.get_or_create(document_number="DEMO-RR-2026-001",defaults={"complaint":complaints[0],"required":True,"checklist":{"serious_event":True,"deadline_reviewed":True},"investigation_result":"조사 진행 중","author":users["raqa"],"reviewer":users["admin"]})
        Approval.objects.get_or_create(content_type="CustomerComplaint",object_id=complaints[0].pk,defaults={"requested_by":users["raqa"]})
        closed, intake = self.seed_software(m, users)
        self.stdout.write(f"가상 소프트웨어 사건 /complaints/{closed.pk}/ (완료), /complaints/{intake.pk}/ (실습)")
        self.stdout.write(self.style.SUCCESS("데모 데이터 생성 완료: admin / raqa / staff"))

    @transaction.atomic
    def seed_software(self, manufacturer, users):
        today = timezone.localdate()
        reviewer, admin = users["raqa"], users["admin"]
        device, _ = MedicalDevice.objects.get_or_create(
            manufacturer=manufacturer, model_number="EEG-SW-DEMO",
            defaults={"name": "뇌파분석 소프트웨어 (가상)", "product_type": "SOFTWARE"},
        )
        udi, _ = UDI.objects.get_or_create(device=device, device_identifier="DEMO-EEG-SW")
        affected, _ = SoftwareRelease.objects.get_or_create(
            device=device, version="v1.2.0", defaults={"released_on": today - timedelta(days=30)},
        )
        fixed, _ = SoftwareRelease.objects.get_or_create(
            device=device, version="v1.2.1", defaults={"released_on": today},
        )
        defaults = {
            "udi": udi, "intake_release": affected, "complaint_type": "RESULT_DELAY",
            "description": "가상 시연: 분석 완료 후 결과 화면 표시가 지연됨.",
            "occurred_on": today, "reporter": users["staff"], "assignee": reviewer,
        }
        case, created = CustomerComplaint.objects.get_or_create(
            device=device, is_example=True, title="[가상] v1.2.0 분석 결과 표시 지연", defaults=defaults,
        )
        intake, _ = CustomerComplaint.objects.get_or_create(
            device=device, is_example=True, title="[가상 실습] v1.2.0 분석 결과 표시 지연", defaults=defaults,
        )
        if not created:
            return case, intake

        for status in ("REVIEW", "AE_DECISION", "RISK"):
            transition_complaint(case, status, reviewer)
        RiskAssessment.objects.create(
            complaint=case, severity=3, probability=4, assessed_by=reviewer,
            rationale="가상 시험에서 표시 지연 재현. 결과값 변조나 유실은 관찰되지 않음.",
        )
        transition_complaint(case, "CAPA_DECISION", reviewer)
        capa = CAPA.objects.create(
            complaint=case, title="분석 결과 갱신 경로 개선", owner=reviewer, due_date=today,
            root_cause="결과 준비 이벤트가 화면 갱신 대기열에서 지연됨.",
            corrective_action="결과 준비 시 화면 갱신을 우선 처리.",
        )
        transition_complaint(case, "REPORT_REVIEW", reviewer)
        RegulatoryReport.objects.create(
            complaint=case, document_number="DEMO-EEG-SW-RR", author=reviewer,
            required=False, checklist={"deadline_reviewed": True},
            investigation_result="RA/QA 가상 판단. 결과값 오류나 위해 사례가 확인되지 않아 규제보고 및 리콜을 진행하지 않기로 검토함.",
        )
        transition_complaint(case, "RECALL_REVIEW", reviewer)
        transition_complaint(case, "APPROVAL", reviewer)
        first = request_complaint_approval(case, reviewer, reason="초기 조사 결과 검토")
        decide_approval(first, admin, "APPROVED", "가상 초기 승인")
        transition_complaint(case, "ACTION_COMPLETE", admin)
        case.affected_releases.set([affected])
        case.impact_rationale = "v1.2.0에서 재현, v1.2.1 회귀 시험에서 재현되지 않음."
        case.save(update_fields=["impact_rationale", "updated_at"])
        evaluate_capa(capa, reviewer, {
            "fixed_release": fixed, "action_result": "가상 회귀 시험 30회에서 결과 표시 지연 없음.",
            "criteria": "분석 완료 후 2초 이내에 결과가 표시되어야 함.",
            "scheduled_on": today, "evaluated_on": today, "verdict": "PASS",
            "rationale": "가상 측정값 모두 기준 이내. 최대 1.4초.",
        })
        close_capa(capa, reviewer)
        try:
            transition_complaint(case, "CLOSED", admin)
        except ValidationError:
            pass
        else:
            raise CommandError("이전 승인으로 소프트웨어 사건을 종료할 수 없습니다.")
        second = request_complaint_approval(case, reviewer, reason="영향 범위 및 v1.2.1 검증 결과 반영")
        decide_approval(second, admin, "APPROVED", "가상 재승인")
        transition_complaint(case, "ACTION_COMPLETE", admin)
        transition_complaint(case, "CLOSED", admin)
        return case, intake
