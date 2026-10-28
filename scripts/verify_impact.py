"""Synthetic end-to-end demonstration in a NEW isolated SQLite/media directory.

Only this fixture mocks a clean scanner response. No legal rules or personal data.
"""
import argparse
import json
import os
import sys
from datetime import time, timedelta
from pathlib import Path
from unittest.mock import patch

parser=argparse.ArgumentParser();parser.add_argument('destination');args=parser.parse_args()
root=Path(args.destination).resolve()
if root.exists(): raise SystemExit('기존 경로는 사용할 수 없습니다. 새 전용 경로를 지정하세요.')
root.mkdir(parents=True)
os.environ.update(DB_ENGINE='sqlite',SQLITE_PATH=str(root/'demo.sqlite3'),PRIVATE_MEDIA_ROOT=str(root/'media'),DJANGO_SETTINGS_MODULE='config.settings')
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import django
django.setup()
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from pms.models import *
from pms.regulation_documents import register_document,extract_document,review_document
from pms.regulatory import *
from pms.impact import create_analysis,process_review
from pms.services import request_complaint_approval,decide_approval,transition_complaint

call_command('migrate',verbosity=0)
users={}
for name,role_name in [('test-author','RA_QA'),('test-approver','ADMIN'),('test-reporter','STAFF')]:
    user=User.objects.create_user(name)
    user.set_password(os.environ['DEMO_PASSWORD']) if os.environ.get('DEMO_PASSWORD') else user.set_unusable_password()
    user.save();Profile.objects.create(user=user,role=role_name);users[role_name]=user
author=users['RA_QA'];admin=users['ADMIN'];staff=users['STAFF']
today=timezone.localdate()
maker=Manufacturer.objects.create(name='TEST ONLY synthetic manufacturer')
device=MedicalDevice.objects.create(manufacturer=maker,name='TEST ONLY instrument',model_number='TEST-NONLEGAL')
udi=UDI.objects.create(device=device,device_identifier='TEST-NONLEGAL-UDI')
case=CustomerComplaint.objects.create(device=device,udi=udi,complaint_type='TEST_EVENT',title='TEST ONLY 영향 분석 시연',description='완전한 가상 사건. 개인정보 없음.',occurred_on=today,reporter=staff,assignee=author,is_example=True,status='APPROVAL')
text='TEST ONLY fictional source. This is not a legal regulation. 모든 항목은 기능 시연 전용이며 실제 보고 의무를 정의하지 않습니다.'
doc=RegulationDocument(title='TEST ONLY 가상 문서',issuer='TEST ONLY',jurisdiction='TEST-REGION',scope_description='TEST only',document_number='TEST-NONLEGAL',edition='TEST-1',effective_on=today-timedelta(days=1),is_example=True,file=SimpleUploadedFile('test.txt',text.encode()))
with override_settings(ANTIVIRUS_COMMAND=['fixture-only']),patch('pms.file_security.subprocess.run') as run:
    run.return_value.returncode=0;doc=register_document(doc,author)
doc=extract_document(doc,author);doc=review_document(doc,admin,'REVIEWED','TEST only synthetic source')
rule=save_draft(ReportingRule(name='TEST ONLY 가상 기한 규칙',jurisdiction='TEST-REGION',device=device,scope_description='TEST only',conditions={'complaint_type':'TEST_EVENT'},reporting_authority='TEST ONLY fictional office',obligation_trigger='TEST event',basis='REPORTED',deadline_expression='TEST ONLY 7 calendar days',days=7,deadline_unit='DAYS',day_type='CALENDAR',include_start=False,deadline_time=time(18),timezone_name='Asia/Seoul',exceptions='TEST ONLY none',effective_on=today-timedelta(days=1),is_example=True),author,'TEST only creation')
for key in FIELD_LABELS: add_citation(rule,author,key,doc.chunks.first(),text,'TEST ONLY manual interpretation','TEST fixture')
def publish(r):
    preview_rule(r,author,f'{today}T10:00:00+09:00')
    r=transition_rule(r,author,'submit','TEST submit');r=transition_rule(r,admin,'approve','TEST approve')
    return transition_rule(r,admin,'activate','TEST activate')
old=publish(rule)
preview=preview_rule(old,author,f'{today}T10:00:00+09:00')
apply_regulated_rule(case,old,author,preview,'TEST original',0,'')
new=revise_rule(old,author,'TEST revision 7 to 2 days');new.days=2;new.deadline_expression='TEST ONLY 2 calendar days'
new=save_draft(new,author,'TEST revision',expected_revision=new.revision)
transition_rule(old,admin,'retire','TEST replacement');new=publish(new)
analysis=create_analysis(old,new,author,inputs={str(case.pk):{'jurisdiction':'TEST-REGION','basis_at':f'{today}T10:00:00+09:00'}})
review=analysis.reviews.get(complaint=case)
process_review(review,author,'IN_PROGRESS','TEST assigned review',author)
process_review(review,author,'APPLIED','TEST explicit reapplication')
case.refresh_from_db()
risk=RiskAssessment.objects.create(complaint=case,severity=2,probability=2,assessed_by=author,rationale='TEST initial')
pending=request_complaint_approval(case,author)
risk.rationale='TEST changed after request';risk.save()
try: decide_approval(pending,admin,'APPROVED')
except ValidationError: blocked=True
else: raise AssertionError('Changed request was accepted')
approved=request_complaint_approval(case,author);decide_approval(approved,admin,'APPROVED')
risk.rationale='TEST changed after approval';risk.save()
try: transition_complaint(case,'ACTION_COMPLETE',admin)
except ValidationError: final_blocked=True
else: raise AssertionError('Stale approval was used')
approved=request_complaint_approval(case,author);decide_approval(approved,admin,'APPROVED')
transition_complaint(case,'ACTION_COMPLETE',admin);transition_complaint(case,'CLOSED',admin)
trace={'synthetic_only':True,'mock_scanner_only':True,'case_id':case.pk,'analysis_id':analysis.pk,'old_rule_id':old.pk,'new_rule_id':new.pk,'shortened':review.shortened,'pending_change_blocked':blocked,'approved_change_blocked':final_blocked,'final_status':case.status,'approval_history_count':Approval.objects.count(),'ui':['/rules/impacts/',f'/rules/impacts/{analysis.pk}/',f'/complaints/{case.pk}/'],'steps':['규정 개정','영향 분석','담당자 검토','기한 비교','명시적 재적용','승인 요청','자료 변경 차단','재승인','최종 조치·종료']}
(root/'demo_trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(trace,ensure_ascii=False,indent=2))
