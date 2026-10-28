from django.contrib import admin
from .models import *
for model in [Profile,Manufacturer,MedicalDevice,UDI,ProductLot,AdverseEvent,PatientAnonymousInfo,RiskAssessment,CAPA,Recall,RecallTarget,RegulatoryReport,AuditLog,Notification,AssistantConversation,AssistantMessage]: admin.site.register(model)

@admin.register(CustomerComplaint)
class ComplaintAdmin(admin.ModelAdmin):
    readonly_fields=('status','version')

@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    readonly_fields=tuple(f.name for f in Approval._meta.fields)
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False

@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    readonly_fields=("scan_status","sha256","detected_type","scanned_at")
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
    def has_add_permission(self,request): return False
