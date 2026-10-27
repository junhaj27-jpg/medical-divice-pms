"""Create explicit sample data and verify PDF + backup in a NEW isolated directory.
No real antivirus claim: only this verification fixture mocks a clean scan result.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

parser=argparse.ArgumentParser();parser.add_argument('destination');args=parser.parse_args()
root=Path(args.destination).resolve()
if root.exists(): raise SystemExit('새 디렉터리를 지정하세요. 기존 데이터는 덮어쓰지 않습니다.')
root.mkdir(parents=True)
os.environ['DB_ENGINE']='sqlite';os.environ['SQLITE_PATH']=str(root/'sample.sqlite3');os.environ['PRIVATE_MEDIA_ROOT']=str(root/'media')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import django
django.setup()
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from PIL import Image,ImageDraw,ImageFont
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pms.models import *
from pms.workflow import *
from pms.regulatory import *
from pms.regulation_documents import register_document,extract_document,review_document
from pms.file_security import scan_attachment
from pms.reporting import generate_report
from pms.backup import backup,restore_verify

call_command('migrate',verbosity=0)
user=User.objects.create_superuser('verification-example')
Profile.objects.create(user=user,role='ADMIN')
ra=User.objects.create_user('verification-ra-example');Profile.objects.create(user=ra,role='RA_QA')
maker=Manufacturer.objects.create(name='예시 제조사 (검증 전용)')
device=MedicalDevice.objects.create(manufacturer=maker,name='예시 의료기기',model_number='EXAMPLE-ONLY')
udi=UDI.objects.create(device=device,device_identifier='EXAMPLE-UDI')
lot=ProductLot.objects.create(device=device,udi=udi,lot_number='EXAMPLE-LOT',distributed_quantity=100)
today=timezone.localdate()
text='이 문장은 한글 줄바꿈과 표의 페이지 넘김을 검증하기 위한 예시 데이터입니다. 실제 환자 또는 실제 의료기기 안전성 판단을 포함하지 않습니다. '
c=CustomerComplaint.objects.create(device=device,udi=udi,lot=lot,reporter=user,title='예시 사건 · PDF·증빙·복구 검증',description=text*22,complaint_type='EXAMPLE',occurred_on=today,is_example=True)
RiskAssessment.objects.create(complaint=c,severity=4,probability=3,assessed_by=user,rationale='예시 위험평가')
RegulatoryReport.objects.create(complaint=c,document_number='EXAMPLE-REPORT',author=user,required=False,checklist={'예시':True},investigation_result=text*5)
task=save_task(WorkTask(complaint=c,assignee=user,title='예시 담당 업무',due_at=timezone.now(),description=text*3),user)
capa=CAPA.objects.create(complaint=c,title='예시 CAPA',owner=user,due_date=today,corrective_action='예시 점검')
evaluate_capa(capa,user,dict(action_result='예시 조치 결과',criteria='예시 기준',scheduled_on=today,evaluated_on=today,verdict='FAIL',rationale='미흡 판정과 재조치 연결 예시'))
evaluate_capa(capa,user,dict(action_result='재조치 후 예시 결과',criteria='추가 점검',scheduled_on=today,evaluated_on=today,verdict='PASS',rationale='재평가 이력을 보존합니다.'))
recall=Recall.objects.create(complaint=c,title='예시 리콜',reason='검증 전용',risk_level='HIGH',device=device,distributed_quantity=100,target_quantity=100,start_date=today,expected_end_date=today,owner=user)
partner=BusinessPartner.objects.create(name='예시 거래처')
row=save_recipient(RecallRecipient(recall=recall,lot=lot,partner=partner,target_quantity=10,unit='개'),user)
record_recovery(row,user,3,today);record_recovery(row,user,4,today)
record_contact(RecallContact(recipient=row,contacted_at=timezone.now(),method='예시 기록 (실제 발송 없음)',note='추가 회수 예정'),user)
# Synthetic, operator-approved fixture data only. Real legal rules are never seeded.
reg_text='테스트 전용 문서. TEST 관할 예시 제품 EXAMPLE 사건은 테스트 기관에 접수 다음날부터 3 달력일, 시작일 미포함, 18:00 Asia/Seoul. 예외 없음. 실제 법정 규정이 아닙니다.'
reg_doc=RegulationDocument(title='테스트 전용 규정',issuer='테스트 발행자',jurisdiction='TEST',scope_description='예시 제품',document_number='TEST-ONLY',edition='TEST-v1',effective_on=today,is_example=True,file=SimpleUploadedFile('test-regulation.txt',reg_text.encode()))
with patch('pms.file_security.subprocess.run',return_value=SimpleNamespace(returncode=0)),patch.object(settings,'ANTIVIRUS_COMMAND',['fixture-only-mocked-scanner']): reg_doc=register_document(reg_doc,ra)
reg_doc=extract_document(reg_doc,ra);reg_doc=review_document(reg_doc,user,'REVIEWED','테스트 원문 검토')
from datetime import time
rule=save_draft(ReportingRule(name='예시·운영 적용 전 검토 필요',jurisdiction='TEST',scope_description='예시 제품',reporting_authority='테스트 기관',obligation_trigger='예시 사건 접수',effective_on=today,conditions={'complaint_type':'EXAMPLE'},basis='REPORTED',days=3,day_type='CALENDAR',deadline_unit='DAYS',include_start=False,deadline_time=time(18),timezone_name='Asia/Seoul',exceptions='없음 (테스트용)',deadline_expression='접수 다음날부터 3 달력일',change_reason='검증 전용 예시',is_example=True),ra,'검증 전용 예시')
chunk=reg_doc.chunks.first()
for field in FIELD_LABELS: add_citation(rule,ra,field,chunk,chunk.text,'테스트 해석·검토','테스트 항목별 근거')
rule.refresh_from_db();preview_rule(rule,ra,f'{today}T10:00:00+09:00');rule=transition_rule(rule,ra,'submit','테스트 검토 요청');rule=transition_rule(rule,user,'approve','테스트 승인');rule=transition_rule(rule,user,'activate','테스트 시행')
preview=preview_rule(rule,ra,f'{today}T10:00:00+09:00');apply_regulated_rule(c,rule,ra,preview,'검증 전용 · 법정 기한 아님',0,str(c.due_date or ''))
font=settings.PDF_KOREAN_FONT
if not font: raise SystemExit('PDF_KOREAN_FONT에 한글 TTF를 지정하세요.')
image=Image.new('RGB',(900,420),'#e4f0f6');draw=ImageDraw.Draw(image)
draw.text((35,70),'예시 이미지 증빙',font=ImageFont.truetype(font,48),fill='#12394b');draw.text((35,160),'실제 운영 자료가 아닙니다.',font=ImageFont.truetype(font,32),fill='#12394b')
buffer=io.BytesIO();image.save(buffer,format='PNG')
pdfmetrics.registerFont(TTFont('EvidenceKorean',font));pdfbytes=io.BytesIO();canvas=Canvas(pdfbytes);canvas.setFont('EvidenceKorean',18);canvas.drawString(50,760,'예시 PDF 증빙 · 병합 검증');canvas.save()
for name,data in [('예시-이미지.png',buffer.getvalue()),('예시-문서.pdf',pdfbytes.getvalue()),('예시-메모.txt','지원하지 않는 본문 병합 형식은 원본 증빙 묶음에 포함됩니다.'.encode())]:
    attachment=Attachment.objects.create(complaint=c,file=SimpleUploadedFile(name,data),original_name=name,uploaded_by=user)
    with patch('pms.file_security.subprocess.run',return_value=SimpleNamespace(returncode=0)),patch.object(settings,'ANTIVIRUS_COMMAND',['fixture-only-mocked-scanner']): scan_attachment(attachment,user)
Attachment.objects.create(complaint=c,file=SimpleUploadedFile('미검사.txt',b'pending'),original_name='미검사 예시 (보고서 포함 차단)',uploaded_by=user)
first=generate_report(c,user);old=Path(first.file.path).read_bytes()
c.title='예시 사건 제목 변경 (다음 버전만 반영)';c.save();second=generate_report(c,user)
assert Path(first.file.path).read_bytes()==old and first.snapshot['complaint']['title']!=second.snapshot['complaint']['title']
(root/'sample-report-v1.pdf').write_bytes(old);(root/'sample-report-v2.pdf').write_bytes(Path(second.file.path).read_bytes())
reader=PdfReader(io.BytesIO(old));extracted='\n'.join(page.extract_text() for page in reader.pages)
assert '의료기기 시판 후 감시 보고서' in extracted and '예시 PDF 증빙' in extracted
assert all('/Annots' not in page for page in reader.pages)
manifest=backup(root/'sample-backup.zip',quiesced=True)
restored=restore_verify(root/'sample-backup.zip',root/'isolated-restore')
assert manifest==restored['files']
result={'example_only':True,'scanner':'mocked only for fixture; not an actual virus scan','pages':len(reader.pages),'versions':[first.version,second.version],'pdf_sha256':hashlib.sha256(old).hexdigest(),'backup_files':len(manifest),'restored_counts':restored['counts'],'recovered_quantity':row.recovered_quantity,'remaining_quantity':row.remaining_quantity}
(root/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
