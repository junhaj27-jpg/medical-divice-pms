from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import exception_handler
from .models import *
from .permissions import IsAdminRole, IsRAQAOrAdmin, RoleWritePermission
from .serializers import *
from .services import audit, decide_approval, role, transition_complaint, visible_complaints
def custom_exception_handler(exc,context):
    response=exception_handler(exc,context)
    if response is not None: response.data={"success":False,"error":{"code":getattr(exc,"default_code","error"),"detail":response.data}}
    return response
class AuditedViewSet(viewsets.ModelViewSet):
    def perform_create(self,s): obj=s.save(); audit(self.request.user,"CREATE",obj,after=s.data,ip=self.request.META.get("REMOTE_ADDR"))
    def perform_update(self,s): before=s.instance.__dict__.copy(); obj=s.save(); audit(self.request.user,"UPDATE",obj,before,s.data,self.request.META.get("REMOTE_ADDR"))
    def perform_destroy(self,obj): audit(self.request.user,"DELETE",obj); obj.delete()
class ManufacturerViewSet(AuditedViewSet): queryset=Manufacturer.objects.all(); serializer_class=ManufacturerSerializer; permission_classes=[RoleWritePermission]; search_fields=["name"]; ordering_fields=["name","created_at"]
class DeviceViewSet(AuditedViewSet): queryset=MedicalDevice.objects.select_related("manufacturer"); serializer_class=DeviceSerializer; permission_classes=[RoleWritePermission]; filterset_fields=["manufacturer","active"]; search_fields=["name","model_number"]
class UDIViewSet(AuditedViewSet): queryset=UDI.objects.select_related("device"); serializer_class=UDISerializer; permission_classes=[RoleWritePermission]; filterset_fields=["device"]; search_fields=["device_identifier"]
class LotViewSet(AuditedViewSet): queryset=ProductLot.objects.select_related("device","udi"); serializer_class=LotSerializer; permission_classes=[RoleWritePermission]; filterset_fields=["device","udi"]; search_fields=["lot_number","serial_number"]
class ComplaintViewSet(AuditedViewSet):
    queryset=CustomerComplaint.objects.none()
    serializer_class=ComplaintSerializer; filterset_fields=["status","device","lot","complaint_type"]; search_fields=["title","description","serial_number"]; ordering_fields=["reported_on","created_at","due_date"]
    def get_queryset(self):
        if getattr(self,"swagger_fake_view",False): return CustomerComplaint.objects.none()
        return visible_complaints(self.request.user)
    def perform_create(self,s): obj=s.save(reporter=self.request.user); audit(self.request.user,"CREATE",obj,after=s.data)
    @action(detail=True,methods=["post"],permission_classes=[IsRAQAOrAdmin])
    def transition(self,request,pk=None):
        obj=transition_complaint(self.get_object(),request.data.get("status"),request.user,request.META.get("REMOTE_ADDR")); return Response(self.get_serializer(obj).data)
class AdverseEventViewSet(AuditedViewSet): queryset=AdverseEvent.objects.select_related("complaint"); serializer_class=AdverseEventSerializer; permission_classes=[RoleWritePermission]; filterset_fields=["serious","event_type"]
class RiskViewSet(AuditedViewSet):
    queryset=RiskAssessment.objects.select_related("complaint"); serializer_class=RiskSerializer; permission_classes=[IsRAQAOrAdmin]
    def perform_create(self,s): obj=s.save(assessed_by=self.request.user); audit(self.request.user,"CREATE",obj,after=s.data)
class CAPAViewSet(AuditedViewSet): queryset=CAPA.objects.select_related("complaint","owner"); serializer_class=CAPASerializer; permission_classes=[IsRAQAOrAdmin]; filterset_fields=["status","owner"]
class RecallViewSet(AuditedViewSet): queryset=Recall.objects.select_related("device","owner"); serializer_class=RecallSerializer; permission_classes=[IsRAQAOrAdmin]; filterset_fields=["risk_level","approval_status","progress_status"]
class ReportViewSet(AuditedViewSet):
    queryset=RegulatoryReport.objects.select_related("complaint"); serializer_class=ReportSerializer; permission_classes=[IsRAQAOrAdmin]
    def perform_create(self,s): obj=s.save(author=self.request.user); audit(self.request.user,"REPORT_CREATE",obj,after=s.data)
class ApprovalViewSet(viewsets.ReadOnlyModelViewSet):
    queryset=Approval.objects.all(); serializer_class=ApprovalSerializer; permission_classes=[IsAdminRole]; filterset_fields=["decision","content_type"]
    @action(detail=True,methods=["post"])
    def decide(self,request,pk=None):
        obj=decide_approval(self.get_object(),request.user,request.data.get("decision"),request.data.get("reason","")); return Response(self.get_serializer(obj).data)
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset=Notification.objects.none()
    serializer_class=NotificationSerializer
    def get_queryset(self):
        if getattr(self,"swagger_fake_view",False): return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)
class AuditViewSet(viewsets.ReadOnlyModelViewSet): queryset=AuditLog.objects.all(); serializer_class=AuditSerializer; permission_classes=[IsAdminRole]; filterset_fields=["action","object_type","actor"]
