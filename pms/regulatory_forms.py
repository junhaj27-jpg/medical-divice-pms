from django import forms
from .forms import StyledForm
from .models import ReportingRule, RegulationDocument, RegulationChunk, MedicalDevice
from .regulatory import FIELD_LABELS
from .regulation_documents import documents_for


class RegulationForm(StyledForm):
    class Meta:
        model=RegulationDocument
        fields=("title","issuer","jurisdiction","device","scope_description","document_number","edition","published_on","effective_on","official_url","file","visibility","is_example")
        widgets={key:forms.DateInput(attrs={"type":"date"}) for key in ("published_on","effective_on")}
        help_texts={"file":"PDF 또는 UTF-8 TXT. 검사 통과 후 추출하며 스캔 PDF는 OCR이 필요할 수 있습니다."}


class RegulatoryRuleForm(StyledForm):
    expected_revision=forms.IntegerField(required=False,widget=forms.HiddenInput)
    class Meta:
        model=ReportingRule
        fields=("name","jurisdiction","device","scope_description","conditions","reporting_authority","obligation_trigger","basis","deadline_expression","days","deadline_unit","day_type","include_start","deadline_time","timezone_name","exceptions","effective_on","effective_until","holidays","holiday_verified_from","holiday_verified_until","holiday_checked_on","unresolved_items","source_expressions","is_example","change_reason")
        widgets={**{key:forms.DateInput(attrs={"type":"date"}) for key in ("effective_on","effective_until","holiday_verified_from","holiday_verified_until","holiday_checked_on")},"deadline_time":forms.TimeInput(attrs={"type":"time","step":"1"}),"scope_description":forms.Textarea(attrs={"rows":3}),"obligation_trigger":forms.Textarea(attrs={"rows":3}),"deadline_expression":forms.Textarea(attrs={"rows":3}),"exceptions":forms.Textarea(attrs={"rows":3}),"change_reason":forms.Textarea(attrs={"rows":3}),"conditions":forms.Textarea(attrs={"rows":3}),"holidays":forms.Textarea(attrs={"rows":3}),"unresolved_items":forms.Textarea(attrs={"rows":3}),"source_expressions":forms.Textarea(attrs={"rows":4})}
        help_texts={"holidays":'[{"date":"YYYY-MM-DD","name":"휴일 명칭"}]. 공휴일 자동 갱신 없음. CSV 가져오기도 지원합니다.',"unresolved_items":"문자열 배열. 해소 시 []로 저장합니다. 필수 항목과 인용은 별도로 다시 검사합니다.","source_expressions":"항목 키별 원문 표현을 보존합니다. 초안 항목이 불명확하면 비워 두세요."}
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        if self.instance.pk: self.initial["expected_revision"]=self.instance.revision
        for key in ("basis","day_type","deadline_unit"): self.fields[key].choices=[("","확인 필요")]+[(k,v) for k,v in self.fields[key].choices if k]
    def clean(self):
        values=super().clean()
        for key,empty in (("conditions",{}),("holidays",[]),("unresolved_items",[]),("source_expressions",{})):
            if values.get(key) is None: values[key]=empty
        return values


class EvidenceSearchForm(forms.Form):
    query=forms.CharField(label="근거 검색어",max_length=300,required=False)
    jurisdiction=forms.CharField(label="관할",max_length=120,required=False)
    device=forms.ModelChoiceField(label="대상 제품 (공통 포함)",queryset=MedicalDevice.objects.all(),required=False)
    edition=forms.CharField(label="문서 버전",max_length=120,required=False)
    as_of=forms.DateField(label="문서 시행 기준일",required=False,widget=forms.DateInput(attrs={"type":"date"}))
    document=forms.ModelChoiceField(label="규정 문서",queryset=RegulationDocument.objects.none(),required=False)
    event_type=forms.CharField(label="사건 유형 (초안 입력용)",max_length=50,required=False)
    def __init__(self,*a,user=None,**kw):
        super().__init__(*a,**kw);self.fields["document"].queryset=documents_for(user)


class CitationForm(forms.Form):
    field_name=forms.ChoiceField(label="연결 항목",choices=list(FIELD_LABELS.items()))
    chunk=forms.ModelChoiceField(label="근거 청크",queryset=RegulationChunk.objects.none(),widget=forms.NumberInput)
    quote=forms.CharField(label="정확한 근거 문장",widget=forms.Textarea)
    interpretation=forms.CharField(label="RA 해석·검토 근거",widget=forms.Textarea,required=False)
    reason=forms.CharField(label="근거 변경 사유",widget=forms.Textarea)
    def __init__(self,*a,user=None,**kw):
        super().__init__(*a,**kw);self.fields["chunk"].queryset=RegulationChunk.objects.filter(document__in=documents_for(user),document__scan_status="PASSED",document__extraction_status="READY")


class PreviewForm(forms.Form):
    basis_at=forms.CharField(label="기준 일시",help_text="YYYY-MM-DDTHH:MM:SS 또는 UTC 오프셋을 포함한 ISO 시각. 오프셋이 없으면 규칙 시간대입니다.")

class ReasonForm(forms.Form): reason=forms.CharField(label="사유",widget=forms.Textarea)

class HolidayImportForm(ReasonForm): file=forms.FileField(label="UTF-8 휴일 CSV (date,name)")

class DocumentReviewForm(ReasonForm):
    decision=forms.ChoiceField(label="문서 검토",choices=[("REVIEWED","검토 완료"),("REJECTED","반려")])
