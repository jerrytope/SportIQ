from django.urls import path

from apps.assessments import views as exam_views

from . import views

app_name = "learning"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("courses/", views.my_learning, name="my_learning"),
    path("achievements/", views.achievements, name="achievements"),
    path("soon/<slug:key>/", views.soon, name="soon"),
    path("notes/<int:note_id>/delete/", views.delete_note, name="delete_note"),
    path("exams/<int:exam_id>/start/", exam_views.start, name="exam_start"),
    path("attempts/<int:pk>/", exam_views.attempt, name="attempt"),
    path("attempts/<int:pk>/autosave/", exam_views.autosave, name="attempt_autosave"),
    path("attempts/<int:pk>/flag/", exam_views.flag, name="attempt_flag"),
    path("attempts/<int:pk>/snapshot/", exam_views.snapshot, name="attempt_snapshot"),
    path("exams/<int:exam_id>/appeal/", exam_views.appeal, name="exam_appeal"),
    path("<slug:slug>/enrol/", views.enrol, name="enrol"),
    path("<slug:slug>/apply/", views.apply, name="apply"),
    path("<slug:slug>/", views.course_home, name="course"),
    path("<slug:slug>/feedback/", views.feedback, name="feedback"),
    path("<slug:slug>/discussions/", views.discussions, name="discussions"),
    path("<slug:slug>/discussions/<int:pk>/", views.thread, name="thread"),
    path("<slug:slug>/preview/<int:pk>/", views.preview, name="preview"),
    path("<slug:slug>/lessons/<int:pk>/", views.lesson, name="lesson"),
    path("<slug:slug>/lessons/<int:pk>/position/", views.save_position, name="save_position"),
    path("<slug:slug>/lessons/<int:pk>/complete/", views.complete, name="complete"),
    path("<slug:slug>/lessons/<int:pk>/notes/", views.add_note, name="add_note"),
    path("<slug:slug>/lessons/<int:pk>/bookmark/", views.toggle_bookmark, name="bookmark"),
]
