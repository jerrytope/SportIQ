from django.urls import path

from . import views

app_name = "integrity"

urlpatterns = [
    path("report/", views.report, name="report"),
    path("status/", views.status, name="status"),
    path("cases/", views.cases, name="cases"),
    path("cases/<int:pk>/", views.case, name="case"),
]
