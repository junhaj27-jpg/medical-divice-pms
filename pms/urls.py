from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import api, views, regulatory_views as regulatory

r=DefaultRouter()
for prefix,view,base in [("manufacturers",api.ManufacturerViewSet,"manufacturer"),("devices",api.DeviceViewSet,"device"),("udis",api.UDIViewSet,"udi"),("lots",api.LotViewSet,"lot"),("complaints",api.ComplaintViewSet,"complaint"),("adverse-events",api.AdverseEventViewSet,"adverse"),("risks",api.RiskViewSet,"risk"),("capas",api.CAPAViewSet,"capa"),("recalls",api.RecallViewSet,"recall"),("recall-targets",api.RecallTargetViewSet,"recall-target"),("reports",api.ReportViewSet,"report"),("attachments",api.AttachmentViewSet,"attachment"),("approvals",api.ApprovalViewSet,"approval"),("notifications",api.NotificationViewSet,"notification"),("audits",api.AuditViewSet,"audit")]: r.register(prefix,view,basename=base)

urlpatterns=[
 path("assistant/",views.assistant_chat,name="assistant-chat"),path("assistant/new/",views.assistant_new,name="assistant-new"),
 path("",views.dashboard,name="dashboard"),path("complaints/",views.complaint_list,name="complaint-list"),path("complaints/new/",views.complaint_create,name="complaint-create"),path("complaints/<int:pk>/",views.complaint_detail,name="complaint-workspace"),
 path("complaints/<int:pk>/transition/",views.complaint_transition,name="complaint-transition"),path("complaints/<int:pk>/risk/",views.risk_save,name="risk-save"),path("complaints/<int:pk>/capa/",views.capa_create,name="capa-create"),path("complaints/<int:pk>/report/",views.report_create,name="report-create"),path("complaints/<int:pk>/recall/",views.recall_create,name="recall-create"),path("complaints/<int:pk>/approval/request/",views.approval_request,name="approval-request"),path("complaints/<int:pk>/approval/<int:approval_pk>/decide/",views.approval_decide,name="approval-decide"),path("complaints/<int:pk>/attachments/",views.attachment_upload,name="attachment-upload"),
 path("devices/",views.device_list,name="device-list"),path("devices/new/",views.device_create,name="device-create"),path("devices/<int:pk>/",views.device_detail,name="device-detail"),path("lots/",views.lot_list,name="lot-list"),path("lots/new/",views.lot_create,name="lot-create"),path("lots/<int:pk>/",views.lot_detail,name="lot-detail"),path("adverse-events/",views.adverse_list,name="adverse-list"),path("adverse-events/new/",views.adverse_create,name="adverse-create"),path("adverse-events/<int:pk>/",views.adverse_detail,name="adverse-detail"),path("capas/",views.capa_list,name="capa-list"),path("capas/<int:pk>/",views.capa_detail,name="capa-detail"),path("recalls/",views.recall_list,name="recall-list"),path("recalls/<int:pk>/",views.recall_detail,name="recall-detail"),path("recalls/<int:pk>/action/",views.recall_admin_action,name="recall-admin-action"),path("recalls/<int:pk>/print/",views.recall_print,name="recall-print"),path("reports/",views.report_list,name="report-list"),path("reports/<int:pk>/print/",views.report_print,name="report-print"),path("approvals/",views.approvals,name="approval-list"),path("notifications/",views.notifications,name="notifications"),path("audits/",views.audit_logs,name="audit-list"),path("users/",views.users,name="user-list"),path("users/<int:pk>/update/",views.user_update,name="user-update"),path("attachments/<int:pk>/download/",views.attachment_download,name="attachment-download"),path("api/",include(r.urls)),
]
from . import workflow_views as workflow
urlpatterns += [
 path("tasks/",workflow.task_list,name="task-list"),
 path("tasks/new/",workflow.task_edit,name="task-create"),
 path("tasks/<int:pk>/",workflow.task_detail,name="task-detail"),
 path("tasks/<int:pk>/edit/",workflow.task_edit,name="task-edit"),
 path("capas/<int:pk>/evaluate/",workflow.capa_evaluate,name="capa-evaluate"),
 path("capas/<int:pk>/close/",workflow.capa_close,name="capa-close"),
 path("recalls/<int:pk>/ledger/",workflow.recall_ledger,name="recall-ledger"),
 path("recalls/<int:recall_pk>/recipients/new/",workflow.recipient_edit,name="recipient-create"),
 path("recalls/<int:recall_pk>/recipients/<int:pk>/",workflow.recipient_edit,name="recipient-edit"),
 path("recipients/<int:pk>/recover/",workflow.recovery_create,name="recovery-create"),
 path("recipients/<int:pk>/contact/",workflow.contact_create,name="contact-create"),
 path("partners/new/",workflow.partner_create,name="partner-create"),
 path("rules/",regulatory.hub,name="rule-list"),
 path("rules/new/",regulatory.rule_new,name="rule-create"),
 path("complaints/<int:pk>/rules/",regulatory.case_apply,name="rule-apply"),
 path("complaints/<int:pk>/pdf/",workflow.artifact_list,name="artifact-list"),
 path("complaints/<int:pk>/pdf/generate/",workflow.artifact_generate,name="artifact-generate"),
 path("pdf/<int:pk>/download/",workflow.artifact_download,name="artifact-download"),
 path("pdf/<int:pk>/evidence/",workflow.artifact_download,{"bundle":True},name="artifact-bundle"),
]

urlpatterns += [
 path("rules/documents/",regulatory.document_list,name="regulation-list"),
 path("rules/documents/new/",regulatory.document_new,name="regulation-create"),
 path("rules/documents/<int:pk>/",regulatory.document_detail,name="regulation-detail"),
 path("rules/documents/<int:pk>/process/",regulatory.document_process,name="regulation-process"),
 path("rules/documents/<int:pk>/review/",regulatory.document_review,name="regulation-review"),
 path("rules/documents/<int:pk>/original/",regulatory.document_original,name="regulation-original"),
 path("rules/search/",regulatory.evidence_search,name="evidence-search"),
 path("rules/from-evidence/",regulatory.from_evidence,name="rule-from-evidence"),
 path("rules/<int:pk>/",regulatory.rule_detail,name="rule-detail"),
 path("rules/<int:pk>/edit/",regulatory.rule_edit,name="rule-edit"),
 path("rules/<int:pk>/action/",regulatory.rule_action,name="rule-action"),
 path("rules/<int:pk>/citations/new/",regulatory.citation_new,name="rule-citation-new"),
 path("rules/citations/<int:pk>/remove/",regulatory.citation_remove,name="rule-citation-remove"),
 path("rules/<int:pk>/holidays/",regulatory.holiday_csv,name="rule-holidays"),
 path("rules/<int:pk>/preview/",regulatory.rule_preview,name="rule-preview"),
 path("rules/<int:pk>/compare/",regulatory.compare_versions,name="rule-compare"),
]

from . import analysis_views
urlpatterns += [
 path('analysis/', analysis_views.dashboard, name='analysis'),
 path('analysis/imports/<int:pk>/', analysis_views.import_detail, name='analysis-import'),
 path('analysis/review/', analysis_views.review, name='analysis-review'),
 path('analysis/reviews/<int:pk>/', analysis_views.review_detail, name='analysis-review-detail'),
]
