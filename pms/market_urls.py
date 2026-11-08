from django.urls import path

from . import market_views as views

urlpatterns = [
    path("markets/", views.dashboard, name="market-dashboard"),
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
