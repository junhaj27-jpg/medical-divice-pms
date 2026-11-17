from django.conf import settings
from django.db import models
from .history import AppendOnlyRecord
from .gs1 import validate_gtin14,human_udi


class GTINNamespace(models.Model):
    gtin_14=models.CharField(primary_key=True,max_length=14,validators=[validate_gtin14])


class ManufacturingSerial(AppendOnlyRecord):
    device=models.ForeignKey("MedicalDevice",on_delete=models.PROTECT,related_name="manufacturing_serials")
    gtin_14=models.CharField(max_length=14,blank=True)
    serial_number=models.CharField(max_length=100)
    manufactured_on=models.DateField(null=True,blank=True)
    issued_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT)
    issued_at=models.DateTimeField(null=True,blank=True)
    recorded_at=models.DateTimeField(auto_now_add=True)
    origin=models.CharField(max_length=12,choices=[("ISSUED","발급"),("LEGACY","기존 자료"),("MANUAL","LOT 입력")])
    request_key=models.UUIDField(null=True,blank=True)
    request_hash=models.CharField(max_length=64,blank=True)
    is_example=models.BooleanField(default=False)

    class Meta:
        ordering=("-pk",)
        constraints=[models.UniqueConstraint(fields=("gtin_14","serial_number"),condition=~models.Q(gtin_14=""),name="manufacturing_gtin_serial_unique"),
                     models.UniqueConstraint(fields=("request_key",),name="manufacturing_serial_request_unique")]

    @property
    def expected_udi(self):
        from django.core.exceptions import ValidationError
        if self.lot_references.count()>1:return ""
        try:return human_udi(self.gtin_14,self.manufactured_on,self.serial_number)
        except ValidationError:return ""

    @property
    def status(self):
        if not self.gtin_14:return "GTIN 미지정"
        if self.lot_references.count()>1:return "기존 중복 · RA 확인 필요"
        return "발급 완료" if self.origin=="ISSUED" else "기존 제조번호"


class SerialLotReference(AppendOnlyRecord):
    serial=models.ForeignKey(ManufacturingSerial,on_delete=models.PROTECT,related_name="lot_references")
    lot=models.ForeignKey("ProductLot",on_delete=models.PROTECT,related_name="serial_history")
    original=models.JSONField()
    recorded_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints=[models.UniqueConstraint(fields=("serial","lot"),name="serial_legacy_lot_reference")]


class SerialDispatchRecord(AppendOnlyRecord):
    serial=models.ForeignKey(ManufacturingSerial,on_delete=models.PROTECT,related_name="dispatches")
    lot=models.ForeignKey("ProductLot",null=True,blank=True,on_delete=models.PROTECT)
    dispatched_on=models.DateField()
    reference=models.CharField(max_length=120)
    expected_udi=models.CharField(max_length=200)
    printed_udi=models.TextField(max_length=500,blank=True)
    note=models.TextField(max_length=2000,blank=True)
    recorded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    recorded_at=models.DateTimeField(auto_now_add=True)


class UDILabelIncident(AppendOnlyRecord):
    serial=models.ForeignKey(ManufacturingSerial,on_delete=models.PROTECT,related_name="label_incidents")
    printed_udi=models.TextField(max_length=500)
    scan_value=models.TextField(max_length=500,blank=True)
    expected_udi=models.CharField(max_length=200)
    differences=models.JSONField()
    task=models.OneToOneField("WorkTask",on_delete=models.PROTECT,related_name="udi_label_incident")
    label_version=models.ForeignKey("LabelVersion",null=True,blank=True,on_delete=models.PROTECT)
    recorded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    recorded_at=models.DateTimeField(auto_now_add=True)


class UDILabelIncidentEvidence(AppendOnlyRecord):
    incident=models.ForeignKey(UDILabelIncident,on_delete=models.PROTECT,related_name="evidence_links")
    attachment=models.ForeignKey("Attachment",on_delete=models.PROTECT)
    original=models.JSONField()


class UDILabelIncidentDispatch(AppendOnlyRecord):
    incident=models.ForeignKey(UDILabelIncident,on_delete=models.PROTECT,related_name="dispatch_links")
    dispatch=models.ForeignKey(SerialDispatchRecord,on_delete=models.PROTECT,related_name="incident_links")
    original=models.JSONField()


class UDILabelFollowup(AppendOnlyRecord):
    incident=models.ForeignKey(UDILabelIncident,on_delete=models.PROTECT,related_name="followups")
    action_type=models.CharField(max_length=20,choices=[("CORRECTION","라벨 정정"),("NOTICE","통보 기록"),("RECALL_REVIEW","회수 검토"),("OTHER","기타")])
    rationale=models.TextField(max_length=4000)
    corrected_udi=models.TextField(max_length=500,blank=True)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    recorded_at=models.DateTimeField(auto_now_add=True)
