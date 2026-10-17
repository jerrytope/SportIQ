from django.urls import path

from . import views

app_name = "careers"

urlpatterns = [
    path("experience/", views.experience, name="experience"),
    path("cv.pdf", views.cv, name="cv"),
    path("challenges/", views.challenges, name="challenges"),
    path("challenges/<int:pk>/", views.challenge, name="challenge"),
    path("challenges/<int:pk>/join/", views.join_challenge, name="join_challenge"),
]
