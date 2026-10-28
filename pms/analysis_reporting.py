"""Render an analysis snapshot with the existing ReportLab dependency."""
import io
from pathlib import Path
from xml.sax.saxutils import escape
from django.conf import settings
from django.core.exceptions import ValidationError
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def analysis_pdf(data, result):
    font = settings.PDF_KOREAN_FONT
    if not font or not Path(font).is_file():
        raise ValidationError('PDF_KOREAN_FONT에 한글 TTF 경로를 설정하세요. 브라우저 인쇄 / PDF 저장도 사용할 수 있습니다.')
    pdfmetrics.registerFont(TTFont('PMSAnalysisKorean', font))
    style = ParagraphStyle('analysis', fontName='PMSAnalysisKorean', fontSize=9, leading=14, wordWrap='CJK')
    title = ParagraphStyle('analysis-title', parent=style, fontSize=16, leading=22)
    story = []

    def text(value, heading=False):
        story.append(Paragraph(escape(str(value)).replace('\n', '<br/>'), title if heading else style))
        story.append(Spacer(1, 6))

    text('PMS 보고 건수 분석 보고서', True)
    text('규제기관 제출 적합성·인과관계를 자동 보증하지 않습니다. AI 해석 없이 관찰 사실과 내부 신호 규칙을 제공합니다.')
    text(f"생성 시각: {result['generated_at'].isoformat()} / 실제·샘플 구분: {data['example']}")
    text(f"날짜 축: {data['basis']} / 분석: {data['start']} ~ {data['end']} / 비교: {result['previous_start']} ~ {result['previous_end']} (동일 길이, 양끝 포함)")
    text(f"적용 필터: {data}")
    text(f"데이터 출처: {', '.join(result['sources']) or '없음'}")
    text(f"현재 보고 건수: {result['total']} / 비교 보고 건수: {result['previous_total']} / 선택 날짜 누락 제외: {result['missing_dates']}")
    text(f"중대성 분포: {result['seriousness']} / 월별 보고 건수: {result['periods']}")
    text(f"신호 기준: 현재 최소 {data['minimum']}건, 증가 {data['threshold']}% 이상. 비교 0건이면 증가율 미산출, 최소 건수 이상 신규 보고 신호.")
    for group in result['groups']:
        increase = str(group['increase']) + '%' if group['increase'] is not None else '미산출 (비교 0건)'
        text(f"{' / '.join(group['device'])}: 현재 {group['count']} / 비교 {group['previous']} / 증가율 {increase}")
    text('검토가 필요한 신호 및 근거', True)
    for signal in result['signals']:
        text(' / '.join(signal['group']['device']))
        review = signal['review']
        text(f"상태: {review.get_status_display() if review else '신규'} / 담당자: {review.assignee.username if review else '미지정'}")
        for evidence in signal['snapshot']['evidence']:
            text(f"레코드 #{evidence['id']} / 출처 {evidence['source']} / 외부 ID {evidence['record_id']} / 수집 #{evidence['batch']} 행 {evidence['row']}: {evidence['quote'] or '근거 문장 부족'}")
        if review:
            for history in review.history.select_related('actor', 'assignee').order_by('pk'):
                text(f'{history.created_at.isoformat()} / {history.actor.username} / {history.before} → {history.after} / 담당자 {history.assignee.username} / {history.note}')
    if not result['signals']: text('검토가 필요한 신호가 없습니다.')
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, title='PMS 보고 건수 분석').build(story)
    return buffer.getvalue()
