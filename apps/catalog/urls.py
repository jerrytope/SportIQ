from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.course_list, name="list"),
    path("paths/", views.path_list, name="paths"),
    path("paths/<slug:slug>/", views.path_detail, name="path_detail"),
    path("<slug:slug>/", views.course_detail, name="course_detail"),
]
