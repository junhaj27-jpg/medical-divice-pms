from django.urls import path

from . import market_views as views
from . import market_review_views as history
from .market_batch_views import batch_compare, offline_demo
from .harmonised_views import standards, product_reviews
from .fda_510k_views import fda_search, fda_product_reviews
from .fda_classification import classification
from .fda_guidance import guidance
from .dental_views import workspace, draft_output, evidence_download, writing_list
from .eu_legal import documents as eu_documents
from .fda_library import library
from . import views as product_views
from . import mri_registration
from . import serial_views
from .source_search_views import source_search,source_document
from . import search_history_views as search_history

from . import dossier_views as dossier

from . import review_task_views as task_reviews
from .workflow_views import task_list as my_tasks, task_detail as scoped_task_detail

from . import product_change_views as product_changes

from . import period_views as periods

urlpatterns = [
    path('markets/pms-analysis/',periods.compare,name='market-pms-compare'),
    path('markets/api/pms-analysis/',periods.compare,{'api':True},name='market-pms-compare-api'),
    path('markets/pms-analysis/snapshots/',periods.listing,name='market-pms-snapshots'),
    path('markets/api/pms-analysis/snapshots/',periods.listing,{'api':True},name='market-pms-snapshots-api'),
    path('markets/pms-analysis/snapshots/<int:pk>/',periods.detail,name='market-pms-snapshot'),
    path('markets/api/pms-analysis/snapshots/<int:pk>/',periods.detail,{'api':True},name='market-pms-snapshot-api'),
    path('markets/pms-analysis/snapshots/<int:pk>/csv/',periods.detail,{'output':'csv'},name='market-pms-csv'),
    path('markets/pms-analysis/snapshots/<int:pk>/tasks/<str:kind>/',periods.task_create,name='market-pms-task'),
    path('markets/api/pms-analysis/snapshots/<int:pk>/tasks/<str:kind>/',periods.task_create,{'api':True},name='market-pms-task-api'),
    path("markets/product-changes/",product_changes.listing,name="market-product-changes-all"),
    path("devices/<int:pk>/markets/product-changes/",product_changes.listing,name="market-product-changes"),
    path("markets/api/devices/<int:pk>/product-changes/",product_changes.listing,{"api":True},name="market-product-changes-api"),
    path("markets/product-changes/<int:pk>/",product_changes.change_detail,name="market-product-change"),
    path("markets/api/product-changes/<int:pk>/",product_changes.change_detail,{"api":True},name="market-product-change-api"),
    path("markets/product-change-reviews/<int:pk>/",product_changes.market_review,name="market-product-change-review"),
    path("markets/api/product-change-reviews/<int:pk>/",product_changes.market_review,{"api":True},name="market-product-change-review-api"),
    path("markets/product-change-reviews/<int:pk>/tasks/",product_changes.task_create,name="market-product-change-task"),
    path("markets/api/product-change-reviews/<int:pk>/tasks/",product_changes.task_create,{"api":True},name="market-product-change-task-api"),
    path("markets/product-change-reviews/<int:pk>/candidates/<str:key>/",product_changes.candidate,name="market-product-change-candidate"),
    path("markets/product-change-reviews/<int:pk>/candidates/<str:key>/original/",product_changes.candidate,{"download":True},name="market-product-change-file"),
    path("markets/api/product-change-reviews/<int:pk>/candidates/<str:key>/",product_changes.candidate,{"api":True},name="market-product-change-candidate-api"),
    path("markets/tasks/",my_tasks,name="market-task-list"),
    path("markets/tasks/<int:pk>/",scoped_task_detail,name="market-task-detail"),
    path("markets/notifications/",task_reviews.notifications,name="market-notifications"),
    path("api/my-tasks/",my_tasks,{"api":True},name="market-my-tasks-api"),
    path("review-tasks/new/<str:kind>/<int:pk>/",task_reviews.create,name="market-review-task-create"),
    path("review-tasks/<int:pk>/",task_reviews.detail,name="market-review-task-detail"),
    path("review-tasks/<int:pk>/evidence/<int:download>/",task_reviews.detail,name="market-review-task-evidence"),
    path("api/review-tasks/new/<str:kind>/<int:pk>/",task_reviews.create,{"api":True},name="market-review-task-create-api"),
    path("api/review-tasks/<int:pk>/",task_reviews.detail,{"api":True},name="market-review-task-api"),
    path("notifications/",task_reviews.notifications,name="notifications"),
    path("notifications/<int:pk>/read/",task_reviews.notifications,name="market-notification-read"),
    path("api/task-notifications/",task_reviews.notifications,{"api":True},name="market-review-notifications-api"),
    path("api/task-notifications/<int:pk>/read/",task_reviews.notifications,{"api":True},name="market-review-notification-read-api"),
    path("markets/ra-documents/",dossier.listing,name="market-ra-documents"),
    path("markets/api/ra-documents/",dossier.listing,{"api":True},name="market-ra-documents-api"),
    path("markets/ra-documents/impacts/",dossier.impact_list,name="market-ra-impacts"),
    path("markets/api/ra-documents/impacts/",dossier.impact_list,{"api":True},name="market-ra-impacts-api"),
    path("markets/ra-documents/<int:pk>/",dossier.detail,name="market-ra-document"),
    path("markets/api/ra-documents/<int:pk>/",dossier.detail,{"api":True},name="market-ra-document-api"),
    path("markets/ra-documents/<int:pk>/<str:output>/",dossier.detail,name="market-ra-document-output"),
    path('markets/ai-search/',source_search,name='market-source-search'),
    path('markets/ai-search/eu/<int:pk>/',search_history.manage_eu,name='market-search-eu-manage'),
    path('markets/ai-search/eu/text/<int:pk>/',search_history.eu_text,name='market-search-eu-text'),
    path('markets/ai-search/eu/text/<int:pk>/original/',search_history.eu_text,{'download':True},name='market-search-eu-original'),
    path('markets/ai-search/executions/<int:pk>/',search_history.execution_detail,name='market-search-execution'),
    path('markets/ai-search/history/',search_history.history,name='market-search-history'),
    path('markets/ai-search/adoptions/<int:pk>/',search_history.adoption_detail,name='market-search-adoption'),
    path('markets/api/ai-search/',source_search,{'api':True},name='market-source-search-api'),
    path('markets/ai-search/documents/<int:pk>/',source_document,name='market-source-document'),
    path('markets/ai-search/documents/<int:pk>/original/',source_document,{'download':True},name='market-source-original'),
    path('devices/<int:pk>/serials/',serial_views.serials,name='market-serials'),
    path('devices/<int:pk>/serials/api/',serial_views.serials,{'api':True},name='market-serial-api'),
    path('devices/<int:pk>/serials/<int:serial_id>/',serial_views.detail,name='market-serial'),
    path('devices/<int:pk>/serials/<int:serial_id>/evidence/new/',serial_views.upload,name='market-serial-upload'),
    path('devices/<int:pk>/udi-incidents/<int:incident_id>/',serial_views.incident_detail,name='market-udi-incident'),
    path('devices/<int:pk>/udi-incidents/<int:incident_id>/evidence/<int:attachment_id>/',serial_views.incident_evidence,name='market-udi-evidence'),
    path("markets/us/devices/new/",product_views.device_create,name="market-device-create"),
    path("markets/us/devices/<int:pk>/",product_views.device_detail,name="market-device-detail"),
    path("markets/us/devices/<int:pk>/edit/",product_views.device_create,name="market-device-edit"),
    path("devices/<int:pk>/markets/us/mri/start/",mri_registration.start,name="market-mri-start"),
    path("devices/<int:pk>/markets/us/mri/documents/new/",mri_registration.upload_document,name="market-mri-upload"),
    path("markets/us/fda-library/", library, name="market-fda-library"),
    path("markets/us/fda-library/<int:pk>/", library, name="market-fda-source"),
    path("markets/eu/legal/", eu_documents, name="market-eu-documents"),
    path("markets/eu/legal/<int:pk>/", eu_documents, name="market-eu-document"),
    path("markets/eu/writing/", writing_list, {"market": "EU"}, name="market-eu-writing-list"),
    path("devices/<int:pk>/markets/eu/writing/", workspace, {"market": "EU"}, name="market-eu-writing"),
    path("devices/<int:pk>/markets/eu/writing/evidence/<int:document_id>/", evidence_download,
         {"market": "EU"}, name="market-eu-writing-evidence"),
    path("markets/us/writing/", writing_list, name="market-writing-list"),
    path("devices/<int:pk>/markets/us/writing/", workspace, name="market-writing"),
    path("devices/<int:pk>/markets/us/dental-510k/", workspace, name="market-dental"),
    path("devices/<int:pk>/markets/us/dental-510k/evidence/<int:document_id>/", evidence_download, name="market-dental-evidence"),
    path("devices/<int:pk>/markets/us/dental-510k/<int:draft_id>/<str:kind>/", draft_output, name="market-dental-output"),
    path("markets/comparisons/<int:pk>/", history.comparison_run, name="market-comparison-run"),
    path("markets/comparisons/<int:pk>/csv/", history.comparison_run, {"download": True},
         name="market-comparison-csv"),
    path("markets/comparison-results/<int:pk>/", history.comparison_result, name="market-comparison-result"),
    path("markets/comparison-results/<int:pk>/task/", history.comparison_task, name="market-comparison-task"),
    path("markets/api/comparison-results/<int:pk>/", history.comparison_result, {"api": True}, name="market-comparison-api"),
    path("complaints/<int:pk>/markets/<str:code>/comparisons/", history.comparison_history, name="market-comparison-history"),
    path("complaints/<int:pk>/markets/<str:code>/snapshots/legacy/", history.operating_snapshot,
         name="market-legacy-snapshot"),
    path("complaints/<int:pk>/markets/<str:code>/snapshots/<int:assessment>/", history.operating_snapshot,
         name="market-operating-snapshot"),
    path("markets/batch/", batch_compare, name="market-batch"),
    path("markets/batch/demo/", offline_demo, name="market-batch-demo"),
    path("markets/batch/<str:code>/", batch_compare, name="market-batch-country"),
    path("markets/", views.dashboard, name="market-dashboard"),
    path("markets/eu/harmonised-standards/", standards, name="market-eu-standards"),
    path("markets/us/fda-510k/", fda_search, name="market-us-fda-510k"),
    path("devices/<int:pk>/markets/us/fda-510k/", fda_product_reviews, name="market-product-fda-510k"),
    path("devices/<int:pk>/markets/us/fda-classification/", classification, name="market-product-fda-classification"),
    path("devices/<int:pk>/markets/us/fda-guidance/", guidance, name="market-product-fda-guidance"),
    path("devices/<int:pk>/markets/eu/harmonised-standards/", product_reviews, name="market-product-standards"),
    path("preferences/language/", views.language, name="market-language"),
    path("devices/<int:pk>/markets/", views.product, name="market-product"),
    path("devices/<int:pk>/markets/<str:code>/", views.registration, name="market-registration"),
    path("devices/<int:pk>/markets/<str:code>/evidence/new/<str:scope>/", views.evidence_new, name="market-evidence-new"),
    path("devices/<int:pk>/markets/<str:code>/evidence/<int:source_pk>/", views.evidence_detail, name="market-evidence"),
    path("devices/<int:pk>/markets/<str:code>/evidence/<int:source_pk>/translation/new/", views.translation_new, name="market-translation-new"),
    path("complaints/<int:pk>/markets/", views.case_detail, name="market-case"),
    path("complaints/<int:pk>/markets/<str:code>/", views.case_country, name="market-case-country"),
    path("complaints/<int:pk>/markets/<str:code>/evaluate/", views.evaluate, name="market-evaluate"),
    path("complaints/<int:pk>/markets/<str:code>/compare/", views.compare, name="market-compare"),
    path("complaints/<int:pk>/markets/<str:code>/report/", views.report, name="market-report"),
    path("complaints/<int:pk>/markets/<str:code>/evidence/<int:source_pk>/", views.case_source, name="market-case-source"),
]
