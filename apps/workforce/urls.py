from django.urls import path

from . import views

app_name = "workforce"

urlpatterns = [
    path("", views.search, name="search"),
    path("me/", views.my_listing, name="my_listing"),
    path("requests/<int:pk>/", views.respond, name="respond"),
    path("contact/<int:user_id>/", views.contact, name="contact"),
    path("skills-map/", views.skills_map, name="skills_map"),
]
