from pathlib import Path
p=Path('pms/analysis_extension_views.py');s=p.read_text(encoding='utf-8').replace('対象と件数を確認してください。','대상과 건수를 명시적으로 확인하세요.').replace('件の新規スナップショットを保存しました。同じ原本バージョンは重複しません。','건의 새 스냅샷을 저장했습니다. 같은 원본 버전은 중복하지 않습니다.').replace('事件番号を確認してください。','사건번호를 확인하세요.');p.write_text(s,encoding='utf-8')
p=Path('pms/urls.py');s=p.read_text(encoding='utf-8');s+='''
from . import analysis_extension_views as analysis_ext
urlpatterns += [
 path('analysis/internal/',analysis_ext.internal_import,name='analysis-internal'),
 path('analysis/internal/<int:pk>/seriousness/',analysis_ext.seriousness,name='analysis-seriousness'),
 path('analysis/artifacts/generate/',analysis_ext.generate_pdf,name='analysis-pdf-generate'),
 path('analysis/artifacts/<int:pk>/',analysis_ext.artifact_download,name='analysis-artifact'),
]
''';p.write_text(s,encoding='utf-8')
p=Path('pms/analysis_views.py');s=p.read_text(encoding='utf-8').replace('from .analysis_models import AnalysisImport, AnalysisReview','from .analysis_models import AnalysisImport, AnalysisReview, AnalysisArtifact');s=s.replace("'report': request.GET", "'artifacts': AnalysisArtifact.objects.select_related('report','generated_by').order_by('-pk')[:30],\n        'report': request.GET");p.write_text(s,encoding='utf-8')
p=Path('pms/analysis_reporting.py');s=p.read_text(encoding='utf-8').replace("    text('PMS 보고 건수 분석 보고서', True)","    text('PMS 보고 건수 분석 보고서 · 발생률 아님', True)\n    archive=result.get('archive_snapshot')\n    if archive:\n        text(f\"보고서 {archive['number']} / 버전 {archive['version']} / 작성자 ID {archive['author_id']}\")\n        text(f\"범위 내용 해시 (SHA-256): {archive['scope_hash']} · 내용 비교용이며 전자서명이 아닙니다.\")");p.write_text(s,encoding='utf-8')
p=Path('pms/templates/pms/analysis.html');s=p.read_text(encoding='utf-8');idx=s.index('{% block content %}')+len('{% block content %}');s=s[:idx]+'''
<p><a href="{% url 'analysis-internal' %}">내부 사건 선택·미리보기·중대성 확인</a></p>
{% if result %}<form method="post" action="{% url 'analysis-pdf-generate' %}">{% csrf_token %}{% for field in form %}<input type="hidden" name="{{field.name}}" value="{{field.value|default_if_none:''}}">{% endfor %}<button>현재 필터의 서버 PDF 새 버전 보관</button></form>{% endif %}
<details><summary>비공개 분석 PDF 버전</summary>{% for a in artifacts %}<p><a href="{% url 'analysis-artifact' a.pk %}">{{a.report.number}} v{{a.version}}</a> · {{a.generated_by}} · {{a.created_at}}</p>{% empty %}<p>보관 버전이 없습니다.</p>{% endfor %}</details>
'''+s[idx:];p.write_text(s,encoding='utf-8')
