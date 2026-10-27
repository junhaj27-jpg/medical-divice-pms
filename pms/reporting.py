"""Server PDFs use only escaped text and verified in-memory private evidence."""
import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, Image, PageBreak
from .models import CustomerComplaint, ReportArtifact
from .services import audit
from .workflow import privileged, recall_totals
from .file_security import safe_attachment_bytes, normalized_name


def snapshot_case(c):
    def rows(qs,fields): return list(qs.values(*fields))
    return json.loads(json.dumps({
        "complaint":{"id":c.pk,"title":c.title,"description":c.description,"status":c.status,"device":str(c.device),"lot":str(c.lot or ""),"reported_on":c.reported_on,"due_date":c.due_date},
        "risk":rows(c.risk_assessment.__class__.objects.filter(complaint=c),["severity","probability","score","level","rationale"]) if hasattr(c,"risk_assessment") else [],
        "regulatory_reports":rows(c.reports.all(),["document_number","required","checklist","investigation_result","status"]),
        "tasks":rows(c.tasks.all(),["id","title","description","assignee__username","priority","status","due_at"]),
        "capas":[{"id":x.pk,"title":x.title,"status":x.status,"action_result":x.action_result,"evaluations":[dict(id=e.pk,action_result=e.action_result,criteria=e.criteria,scheduled_on=e.scheduled_on,evaluator=e.evaluator.username,evaluated_on=e.evaluated_on,verdict=e.verdict,rationale=e.rationale,evidence_ids=list(e.evidence.values_list("pk",flat=True))) for e in x.evaluations.all()]} for x in c.capas.all()],
        "recalls":[{"id":x.pk,"title":x.title,"totals":recall_totals(x),"legacy_quantity":{"target":x.target_quantity,"recovered":x.recovered_quantity,"note":"기존 집계(원장과 합산하지 않음)"},"recipients":[{"partner":str(r.partner),"lot":str(r.lot),"unit":r.unit,"target":r.target_quantity,"recovered":r.recovered_quantity,"remaining":r.remaining_quantity,"unrecovered_reason":r.unrecovered_reason,"notified_on":r.notified_on,"notification_method":r.notification_method,"replied_on":r.replied_on,"reply_status":r.reply_status,"recoveries":rows(r.recoveries.all(),["recovered_on","quantity"]),"contacts":rows(r.contacts.all(),["contacted_at","method","note"])} for r in x.recipients.all()]} for x in c.recalls.all()],
        "rules":rows(c.rule_applications.all(),["snapshot","due_at","reason","created_at"]),
        "evidence":rows(c.attachments.all(),["id","original_name","sha256","scan_status","detected_type"]),
    },default=str,ensure_ascii=False))


def build_pdf(snapshot,number,version,creator,evidence):
    font=settings.PDF_KOREAN_FONT
    if not font or not Path(font).is_file(): raise ValidationError("PDF_KOREAN_FONT에 한글 TTF 글꼴 경로를 설정하세요.")
    pdfmetrics.registerFont(TTFont("PMSKorean",font))
    styles=getSampleStyleSheet()
    body=ParagraphStyle("Korean",fontName="PMSKorean",fontSize=9,leading=14,wordWrap="CJK",spaceAfter=5)
    heading=ParagraphStyle("KoreanHeading",parent=body,fontSize=14,leading=20,spaceBefore=12)
    def p(value,style=body): return Paragraph(escape(str(value)).replace("\n","<br/>"),style)
    labels={"id":"번호","title":"제목","description":"설명","status":"상태","device":"제품","lot":"로트","reported_on":"접수일","due_date":"처리 기한","severity":"심각도","probability":"발생 가능성","score":"위험점수","level":"위험등급","rationale":"판정 근거","document_number":"문서번호","required":"보고 필요","checklist":"체크리스트","investigation_result":"조사 결과","assignee__username":"담당자","priority":"우선순위","due_at":"마감 시각","action_result":"조치 결과","evaluations":"평가 이력","criteria":"평가 기준","scheduled_on":"평가 예정일","evaluator":"평가자","evaluated_on":"평가일","verdict":"판정","evidence_ids":"증빙 번호","totals":"단위별 합계","target":"대상 수량","recovered":"회수 수량","remaining":"미회수 수량","legacy_quantity":"기존 수기 집계","note":"비고","recipients":"거래처별 대상","partner":"거래처","unit":"단위","unrecovered_reason":"미회수 사유","notified_on":"통보일","notification_method":"통보 방법","replied_on":"회신일","reply_status":"회신 상태","recoveries":"회수 이력","recovered_on":"회수일","quantity":"수량","contacts":"연락 이력","contacted_at":"연락 일시","method":"방법","snapshot":"적용 규칙 스냅샷","name":"규칙명","version":"버전","conditions":"조건","complaint_type":"불만 유형","risk_level":"위험등급","serious":"중대 여부","basis":"기준 시점","days":"기한 일수","day_type":"달력 기준","holidays":"휴일 달력","is_example":"예시 여부","effective_on":"시행일","basis_date":"계산 기준일","timezone":"시간대","reason":"적용 사유","created_at":"기록 일시","original_name":"원본 파일명","sha256":"SHA-256","scan_status":"검사 상태","detected_type":"실제 형식"}
    values={"RECEIVED":"접수","WAITING":"대기","IN_PROGRESS":"진행 중","REVIEW":"검토 중","DONE":"완료","EFFECTIVENESS":"효과확인","PASS":"적합","FAIL":"미흡","PASSED":"검사 통과","PENDING":"검사 대기","FAILED":"검사 실패","QUARANTINED":"격리","REPORTED":"접수일","OCCURRED":"발생일","CALENDAR":"달력일","BUSINESS":"영업일","NORMAL":"보통","HIGH":"높음","CRITICAL":"매우 높음"}
    story=[p("의료기기 시판 후 감시 보고서",heading),p(f"{number} / 버전 {version} / 생성자 {creator} / {timezone.localtime():%Y-%m-%d %H:%M %Z}"),p("포트폴리오용 · 규제 제출 또는 의료 판단을 대신하지 않습니다.")]
    def section(title,value):
        story.append(p(title,heading))
        def flatten(v,prefix=""):
            result=[]
            if isinstance(v,dict):
                for k,val in v.items(): result.extend(flatten(val,f"{prefix} / {labels.get(k,k)}" if prefix else labels.get(k,k)))
            elif isinstance(v,list):
                if not v: result.append([p(prefix),p("없음")])
                for index,item in enumerate(v,1): result.extend(flatten(item,f"{prefix} [{index}]"))
            else:
                # Split very long cells into bounded chunks so no row exceeds a page.
                text="미입력" if v is None else "예" if v is True else "아니요" if v is False else values.get(str(v),str(v))
                for start in range(0,max(len(text),1),400): result.append([p(prefix),p(text[start:start+400])])
            return result
        rows=[[p("항목"),p("생성 시점 내용")]]+flatten(value)
        table=LongTable(rows,colWidths=[160,335],repeatRows=1,hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e3eff5")),("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6)]))
        story.append(table)
    for key,title in [("complaint","사건 요약"),("risk","위험평가"),("regulatory_reports","규제보고 판단"),("tasks","담당 업무"),("capas","CAPA 효과성 평가"),("recalls","리콜 회수 현황"),("rules","적용 보고 규칙"),("evidence","첨부 증빙 목록")]: section(title,snapshot[key])
    for name,kind,data in evidence:
        if kind in ("png","jpeg"):
            story.extend([PageBreak(),p(f"이미지 증빙: {name}",heading)])
            img=Image(io.BytesIO(data)); img._restrictSize(490,620); story.append(img)
    output=io.BytesIO()
    def footer(canvas,doc):
        canvas.setFont("PMSKorean",8); canvas.drawString(40,24,f"{number} v{version} · {doc.page}")
    SimpleDocTemplate(output,pagesize=(595.28,841.89),leftMargin=45,rightMargin=45,topMargin=40,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    writer=PdfWriter(); writer.append(PdfReader(io.BytesIO(output.getvalue())),import_outline=False)
    for name,kind,data in evidence:
        if kind=="pdf":
            reader=PdfReader(io.BytesIO(data))
            # Import static page content only. No actions, forms, links, or embedded files.
            for page in reader.pages:
                for key in ("/Annots","/AA"): page.pop(key,None)
                writer.add_page(page)
    merged=io.BytesIO(); writer.write(merged); return merged.getvalue()


@transaction.atomic
def generate_report(complaint,user):
    privileged(user)
    c=CustomerComplaint.objects.select_for_update().get(pk=complaint.pk)
    snapshot=snapshot_case(c); evidence=[]
    for attachment in c.attachments.filter(scan_status="PASSED"):
        evidence.append((f"{attachment.pk}-{normalized_name(attachment.original_name)}",attachment.detected_type,safe_attachment_bytes(attachment)))
    version=(c.artifacts.order_by("-version").values_list("version",flat=True).first() or 0)+1
    number=f"PMS-{c.pk:06d}"
    data=build_pdf(snapshot,number,version,user.username,evidence)
    bundle=io.BytesIO()
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json",json.dumps(snapshot,ensure_ascii=False,indent=2))
        for name,kind,content in evidence: z.writestr(name,content)
    artifact=ReportArtifact(complaint=c,number=number,version=version,snapshot=snapshot,generated_by=user,sha256=hashlib.sha256(data).hexdigest(),bundle_sha256=hashlib.sha256(bundle.getvalue()).hexdigest())
    token=uuid.uuid4().hex
    artifact.file.save(f"{number}-v{version}-{token}.pdf",ContentFile(data),save=False)
    try:
        artifact.bundle.save(f"{number}-v{version}-{token}.zip",ContentFile(bundle.getvalue()),save=False)
        artifact.save()
    except Exception:
        artifact.file.delete(save=False); artifact.bundle.delete(save=False); raise
    audit(user,"PDF_GENERATE",artifact,after={"version":version,"sha256":artifact.sha256})
    return artifact
