"""Render only the preserved periodic snapshot, without querying live source records."""
import io
import json
from pathlib import Path
from xml.sax.saxutils import escape
from django.conf import settings
from django.core.exceptions import ValidationError
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def render_periodic(snapshot, version, reviewer_id, review_note):
    if not settings.PDF_KOREAN_FONT or not Path(settings.PDF_KOREAN_FONT).is_file():
        raise ValidationError('확정 PDF 보존을 위해 PDF_KOREAN_FONT에 한글 TTF를 설정하세요.')
    pdfmetrics.registerFont(TTFont('PMSPeriodic', settings.PDF_KOREAN_FONT))
    style=ParagraphStyle('body',fontName='PMSPeriodic',fontSize=9,leading=14,wordWrap='CJK')
    heading=ParagraphStyle('heading',parent=style,fontSize=14,leading=20,spaceAfter=10)
    story=[]
    def text(value, title=False):
        story.extend([Paragraph(escape(str(value)).replace('\n','<br/>'),heading if title else style),Spacer(1,6)])
    text('내부 PMS 정기 검토 보고서',True)
    text(f"확정 버전 {version} / 작성자 ID {snapshot['author_id']} / 검토자 ID {reviewer_id}")
    text(f"제품 {snapshot['device']['name']} / 모델 {snapshot['device']['model']} / UDI {', '.join(snapshot['device']['udis'])}")
    text(f"기간 {snapshot['start']} - {snapshot['end']} / 직전 {snapshot['previous_start']} - {snapshot['previous_end']}")
    text(f"현재 상태 기준 {snapshot['as_of']} / {'예시' if snapshot['is_example'] else '실제'} 데이터")
    text(f'검토 의견: {review_note}')
    for metric in snapshot['metrics']:
        text(f"{metric['label']}: {metric['count']} {metric.get('count_unit','건')}",True)
        if metric.get('inclusion'): text(metric['inclusion'])
        for ref in metric['evidence']:
            text(f"{ref['label']} / {ref['url']}")
            if ref.get('detail'): text(json.dumps(ref['detail'],ensure_ascii=False,default=str))
    text('누락·제외·해석 한계',True)
    for limit in snapshot['limits']: text(limit)
    def footer(canvas, doc):
        canvas.setFont('PMSPeriodic',8)
        canvas.drawString(42,25,f'내부 검토용 / v{version} / {doc.page}')
    output=io.BytesIO()
    SimpleDocTemplate(output,title='내부 PMS 정기 검토 보고서',leftMargin=42,rightMargin=42,topMargin=42,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
