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
    class Meta: model=MedicalDevice; fields=("manufacturer","name","model_number","gtin_14","risk_class","product_type","active")
    intended_use = forms.CharField(label="사용목적 (영문)", max_length=1500, required=False, widget=forms.Textarea)
    target_population = forms.CharField(label="대상 환자군", max_length=400, required=False)
    users = forms.CharField(label="사용자", max_length=400, required=False)
    environment = forms.CharField(label="사용 환경", max_length=400, required=False)
    configuration_name = forms.CharField(label="모델 구성 식별명", max_length=160, required=False)
    field_strength_t = forms.DecimalField(label="자장 세기 (T) · 미확인 시 비움", max_digits=7, decimal_places=3, min_value=0.001, required=False)
    magnet_type = forms.CharField(label="자석 유형", max_length=100, required=False)
    rf_coil = forms.CharField(label="RF 코일 · 모델/구성", max_length=400, required=False)
    modes = forms.CharField(label="주요 촬영 모드", max_length=400, required=False)
    accessories = forms.CharField(label="구성품·액세서리", max_length=2000, required=False, widget=forms.Textarea)
    software_version = forms.CharField(label="소프트웨어 버전", max_length=100, required=False)
    is_example = forms.BooleanField(label="예시 자료 (DEMO- 모델)", required=False)
    family = forms.ModelChoiceField(queryset=MedicalDevice.objects.filter(product_type="MRI"), required=False, widget=forms.HiddenInput)
    configuration_revision = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, user=None, **kwargs):
        self.actor = user
        super().__init__(*args, **kwargs)
        from .market_service import scoped, product_markets
        if user and scoped(user):
            self.fields["family"].queryset = self.fields["family"].queryset.filter(pk__in=product_markets(user).filter(market="US").values("device_id"))
        self.configuration = self.instance.mri_configurations.first() if self.instance.pk else None
        if self.configuration:
            for key in self.mri_fields():
                self.initial[key] = getattr(self.configuration, key)
            self.initial.update(family=self.configuration.family_id, configuration_revision=self.configuration.pk)

    @staticmethod
    def mri_fields():
        return ("configuration_name", "intended_use", "target_population", "users", "environment", "field_strength_t",
                "magnet_type", "rf_coil", "modes", "accessories", "software_version", "is_example")

    def clean(self):
        data = super().clean()
        if self.configuration and data.get("product_type") != "MRI":
            self.add_error("product_type", "MRI 구성 이력이 있는 제품의 유형은 변경할 수 없습니다.")
        if data.get("product_type") == "MRI":
            for key in ("configuration_name", "intended_use", "target_population", "users", "environment"):
                if not data.get(key): self.add_error(key, "MRI 장비 등록에 필요한 항목입니다.")
            if data.get("is_example") and not data.get("model_number", "").startswith("DEMO-"):
                self.add_error("model_number", "예시 모델은 DEMO-로 시작해야 합니다.")
            if self.configuration and data.get("configuration_revision") != self.configuration.pk:
                self.add_error(None, "구성 정보가 변경됐습니다. 최신 화면을 다시 열어 저장하세요.")
            family = data.get("family")
            if family and family.manufacturer_id != getattr(data.get("manufacturer"), "pk", None):
                self.add_error("manufacturer", "같은 장비의 추가 모델은 동일 제조사에 연결하세요.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=commit)
        if commit and obj.product_type == "MRI":
            from .mri_models import MRIConfiguration
            values = {key:self.cleaned_data[key] for key in self.mri_fields()}
            old = self.configuration
            if not old or any(getattr(old, key) != value for key,value in values.items()):
                MRIConfiguration.objects.create(device=obj, family=self.cleaned_data.get("family") or (old.family if old else obj),
                    version=old.version+1 if old else 1, recorded_by=self.actor, **values)
        return obj
class LotForm(StyledForm):
    class Meta: model=ProductLot; fields=("device","udi","lot_number","serial_number","manufactured_on","expires_on","distributed_quantity")
class AdverseEventForm(StyledForm):
    class Meta: model=AdverseEvent; fields=("complaint","patient","event_type","outcome","serious","narrative")
