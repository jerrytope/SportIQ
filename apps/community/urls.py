from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    path("", views.home, name="home"),
    path("groups/<slug:slug>/", views.group, name="group"),
    path("groups/<slug:slug>/join/", views.join, name="join"),
    path("groups/<slug:slug>/members/<int:user_id>/", views.approve_member, name="approve_member"),
    path("discussions/<int:pk>/", views.discussion, name="discussion"),
    path("report/<str:kind>/<int:pk>/", views.report, name="report"),
    path("mentors/", views.mentors, name="mentors"),
    path("mentors/<int:pk>/request/", views.request_mentor, name="request_mentor"),
    path("mentorships/<int:pk>/", views.mentorship_action, name="mentorship_action"),
    path("opportunities/", views.opportunities, name="opportunities"),
    path("opportunities/new/", views.post_opportunity, name="post_opportunity"),
    path("opportunities/mine/", views.my_postings, name="my_postings"),
    path("opportunities/<int:pk>/", views.opportunity, name="opportunity"),
    path("opportunities/<int:pk>/applicants/", views.applicants, name="applicants"),
    path("pro/<int:user_id>/", views.profile, name="profile"),
]
