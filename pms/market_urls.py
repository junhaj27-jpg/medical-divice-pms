from django.urls import path

from . import market_views as views
from . import market_review_views as history
from .market_batch_views import batch_compare, offline_demo
from .harmonised_views import standards, product_reviews
from .fda_510k_views import fda_search, fda_product_reviews
from .fda_classification import classification
from .fda_guidance import guidance

urlpatterns = [
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
