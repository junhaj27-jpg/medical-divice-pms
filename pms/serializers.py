from rest_framework import serializers
from .models import *
class ManufacturerSerializer(serializers.ModelSerializer):
    class Meta: model=Manufacturer; fields="__all__"
class DeviceSerializer(serializers.ModelSerializer):
    manufacturer_name=serializers.CharField(source="manufacturer.name",read_only=True)
    class Meta: model=MedicalDevice; fields="__all__"
class UDISerializer(serializers.ModelSerializer):
    class Meta: model=UDI; fields="__all__"
class LotSerializer(serializers.ModelSerializer):
    class Meta: model=ProductLot; fields="__all__"
class ComplaintSerializer(serializers.ModelSerializer):
    reporter=serializers.PrimaryKeyRelatedField(read_only=True); risk_level=serializers.CharField(source="risk_assessment.level",read_only=True)
    class Meta: model=CustomerComplaint; fields="__all__"; read_only_fields=("status","version")
    def validate(self,data):
        if data.get("udi") and data.get("device") and data["udi"].device_id!=data["device"].id: raise serializers.ValidationError("UDI가 선택한 의료기기에 속하지 않습니다.")
        if data.get("lot") and data.get("device") and data["lot"].device_id!=data["device"].id: raise serializers.ValidationError("LOT가 선택한 의료기기에 속하지 않습니다.")
        return data
class AdverseEventSerializer(serializers.ModelSerializer):
    class Meta: model=AdverseEvent; fields="__all__"
class RiskSerializer(serializers.ModelSerializer):
    score=serializers.IntegerField(read_only=True); level=serializers.CharField(read_only=True); capa_review_required=serializers.BooleanField(read_only=True); assessed_by=serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta: model=RiskAssessment; fields="__all__"
class CAPASerializer(serializers.ModelSerializer):
    class Meta: model=CAPA; fields="__all__"
class RecallSerializer(serializers.ModelSerializer):
    recovery_rate=serializers.FloatField(read_only=True)
    class Meta: model=Recall; fields="__all__"
    def validate(self,data):
        if data.get("target_quantity",getattr(self.instance,"target_quantity",0))>data.get("distributed_quantity",getattr(self.instance,"distributed_quantity",0)): raise serializers.ValidationError("회수 목표 수량은 유통 수량을 초과할 수 없습니다.")
        if data.get("recovered_quantity",getattr(self.instance,"recovered_quantity",0))>data.get("target_quantity",getattr(self.instance,"target_quantity",0)): raise serializers.ValidationError("실제 회수 수량은 목표 수량을 초과할 수 없습니다.")
        return data
class ReportSerializer(serializers.ModelSerializer):
    class Meta: model=RegulatoryReport; fields="__all__"; read_only_fields=("author","approved_by","approved_at")
class ApprovalSerializer(serializers.ModelSerializer):
    class Meta: model=Approval; fields="__all__"; read_only_fields=("decided_by","decided_at")
class NotificationSerializer(serializers.ModelSerializer):
    class Meta: model=Notification; fields="__all__"; read_only_fields=("user",)
class AuditSerializer(serializers.ModelSerializer):
    class Meta: model=AuditLog; fields="__all__"
