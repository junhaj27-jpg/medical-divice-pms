from django import forms
from .models import AdverseEvent, Attachment, CAPA, CustomerComplaint, MedicalDevice, ProductLot, Recall, RegulatoryReport, RiskAssessment
class StyledForm(forms.ModelForm):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        for f in self.fields.values(): f.widget.attrs["class"]="form-control"
class ComplaintForm(StyledForm):
    class Meta: model=CustomerComplaint; exclude=("reporter","status","version")
class RiskForm(StyledForm):
    class Meta: model=RiskAssessment; exclude=("score","level","capa_review_required","assessed_by")
class RecallForm(StyledForm):
    class Meta: model=Recall; fields=("title","reason","risk_level","distributed_quantity","target_quantity","recovered_quantity","start_date","expected_end_date")
class CAPAForm(StyledForm):
    class Meta: model=CAPA; fields=("title","root_cause","corrective_action","preventive_action","owner","due_date")
class ReportForm(StyledForm):
    serious_event=forms.BooleanField(required=False,label="중대 이상사례")
    health_deterioration=forms.BooleanField(required=False,label="중대한 건강 악화")
    recurrence_possible=forms.BooleanField(required=False,label="재발 가능성")
    deadline_reviewed=forms.BooleanField(required=True,label="보고 기한 검토 완료")
    class Meta: model=RegulatoryReport; fields=("required","investigation_result")
class AttachmentForm(StyledForm):
    class Meta: model=Attachment; fields=("file",)
class DeviceForm(StyledForm):
    class Meta: model=MedicalDevice; fields=("manufacturer","name","model_number","risk_class","active")
class LotForm(StyledForm):
    class Meta: model=ProductLot; fields=("device","udi","lot_number","serial_number","manufactured_on","expires_on","distributed_quantity")
class AdverseEventForm(StyledForm):
    class Meta: model=AdverseEvent; fields=("complaint","patient","event_type","outcome","serious","narrative")
