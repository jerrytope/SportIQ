from django.urls import path

from . import views

app_name = "live"

urlpatterns = [
    path("", views.index, name="index"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/register/", views.register, name="register"),
    path("<int:pk>/join/", views.join, name="join"),
    path("<int:pk>/ask/", views.ask, name="ask"),
    path("<int:pk>/polls/new/", views.poll_create, name="poll_create"),
    path("questions/<int:qid>/", views.question_action, name="question_action"),
    path("polls/<int:poll_id>/vote/", views.vote, name="vote"),
    path("office-hours/<int:slot_id>/book/", views.book_slot, name="book_slot"),
]
