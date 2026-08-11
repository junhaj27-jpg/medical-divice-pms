from django.contrib import admin
from .models import *
for model in [Profile,Manufacturer,MedicalDevice,UDI,ProductLot,CustomerComplaint,AdverseEvent,PatientAnonymousInfo,RiskAssessment,CAPA,Recall,RecallTarget,RegulatoryReport,Attachment,Approval,AuditLog,Notification]: admin.site.register(model)
