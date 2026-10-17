from django.urls import path

from . import views

app_name = "research"

urlpatterns = [
    path("", views.index, name="index"),
    path("projects/new/", views.project_new, name="project_new"),
    path("projects/<slug:slug>/", views.project, name="project"),
    path("datasets/<int:pk>/request/", views.dataset_request, name="dataset_request"),
    path("datasets/<int:pk>/download/", views.dataset_download, name="dataset_download"),
    path("publications/new/", views.publication_new, name="publication_new"),
    path("publications/<int:pk>/", views.publication, name="publication"),
    path("reviews/<int:pk>/", views.review, name="review"),
    path("outcomes/<int:pk>/", views.outcome_survey, name="outcome_survey"),
]
