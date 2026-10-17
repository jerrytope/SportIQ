from django.urls import path

from . import views

app_name = "labs"

urlpatterns = [
    path("", views.index, name="index"),
    path("runs/<int:pk>/", views.result, name="result"),
    path("<slug:slug>/", views.play, name="play"),
]
