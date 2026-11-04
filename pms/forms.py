from django import forms
from .models import AdverseEvent, Attachment, CAPA, CustomerComplaint, MedicalDevice, ProductLot, Recall, RegulatoryReport, RiskAssessment, SoftwareRelease
class StyledForm(forms.ModelForm):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        for f in self.fields.values(): f.widget.attrs["class"]="form-control"
class ComplaintForm(StyledForm):
    class Meta:
        model = CustomerComplaint
        exclude = ("reporter", "status", "version", "affected_releases", "impact_rationale")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        device = self.data.get("device", "")
        self.fields["intake_release"].queryset = SoftwareRelease.objects.filter(device_id=device) if device.isascii() and device.isdecimal() and len(device) < 19 else SoftwareRelease.objects.none()
        self.fields["intake_release"].empty_label = "버전 미확인"

class SoftwareReleaseForm(StyledForm):
    class Meta:
        model = SoftwareRelease
        fields = ("version", "released_on")
        widgets = {"released_on": forms.DateInput(attrs={"type": "date"})}

class SoftwareImpactForm(StyledForm):
    class Meta:
        model = CustomerComplaint
        fields = ("intake_release", "affected_releases", "impact_rationale")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        releases = self.instance.device.software_releases.all()
        self.fields["affected_releases"].queryset = releases
        self.fields["intake_release"].queryset = releases
        self.fields["intake_release"].empty_label = "버전 미확인"
        self.fields["intake_release"].disabled = bool(self.instance.intake_release_id)

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
    class Meta: model=MedicalDevice; fields=("manufacturer","name","model_number","risk_class","product_type","active")
class LotForm(StyledForm):
    class Meta: model=ProductLot; fields=("device","udi","lot_number","serial_number","manufactured_on","expires_on","distributed_quantity")
class AdverseEventForm(StyledForm):
    class Meta: model=AdverseEvent; fields=("complaint","patient","event_type","outcome","serious","narrative")
