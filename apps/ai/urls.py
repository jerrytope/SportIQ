from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path("", views.assistant, name="assistant"),
    path("c/<int:pk>/", views.assistant, name="conversation"),
    path("ask/", views.ask, name="ask"),
    path("messages/<int:msg_id>/rate/", views.rate, name="rate"),
    path("study-plan/", views.study_plan, name="study_plan"),
    path("revise/", views.revise, name="revise"),
    path("help/", views.support_chat, name="support"),
    path("help/<int:pk>/", views.support_chat, name="support_chat"),
]
