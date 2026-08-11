from django import forms
from .models import Attachment, CustomerComplaint, Recall, RiskAssessment
class StyledForm(forms.ModelForm):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        for f in self.fields.values(): f.widget.attrs["class"]="form-control"
class ComplaintForm(StyledForm):
    class Meta: model=CustomerComplaint; exclude=("reporter","status","version")
class RiskForm(StyledForm):
    class Meta: model=RiskAssessment; exclude=("score","level","capa_review_required","assessed_by")
class RecallForm(StyledForm):
    class Meta: model=Recall; fields=("title","reason","risk_level","device","distributed_quantity","target_quantity","recovered_quantity","start_date","expected_end_date","owner")
class AttachmentForm(StyledForm):
    class Meta: model=Attachment; fields=("file",)
