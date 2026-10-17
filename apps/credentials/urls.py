from django.urls import path

from . import views, views_lifecycle as lc

app_name = "credentials"

urlpatterns = [
    path("credentials/", views.wallet, name="wallet"),
    path("credentials/transcript.pdf", views.transcript, name="transcript"),
    path("credentials/portfolio.pdf", lc.portfolio, name="portfolio"),
    path("credentials/cpd/", lc.cpd, name="cpd"),
    path("credentials/programmes/", lc.programmes, name="programmes"),
    path("credentials/programmes/<slug:slug>/", lc.programme, name="programme"),
    path("credentials/prior-learning/<slug:slug>/", lc.rpl_claim, name="rpl"),
    path("credentials/external/", lc.external, name="external"),
    path("credentials/<uuid:pk>/", views.detail, name="detail"),
    path("credentials/<uuid:pk>/certificate.pdf", views.pdf, name="pdf"),
    path("credentials/<uuid:pk>/renew/", lc.request_renewal, name="renew"),
    path("credentials/<uuid:pk>/badge.json", lc.badge_json, name="badge"),
    path("verify/", views.verify, name="verify"),
    path("verify/<str:code>/", views.verify_code, name="verify_code"),
]
