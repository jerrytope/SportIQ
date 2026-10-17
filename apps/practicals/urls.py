from django.urls import path

from . import views

app_name = "practicals"

urlpatterns = [
    path("tasks/<int:pk>/", views.task_view, name="task"),
    path("submissions/<int:pk>/", views.submission, name="submission"),
    path("supervisor/<str:token>/", views.signoff, name="signoff"),
]
