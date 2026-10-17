from django.urls import path

from . import views

app_name = "library"

urlpatterns = [
    path("", views.index, name="index"),
    path("my/", views.collections, name="collections"),
    path("<slug:slug>/", views.detail, name="detail"),
    path("<slug:slug>/download/", views.download, name="download"),
    path("<slug:slug>/cite/<str:style>/", views.cite, name="cite"),
    path("<slug:slug>/annotate/", views.annotate, name="annotate"),
    path("<slug:slug>/collect/", views.collect, name="collect"),
]
