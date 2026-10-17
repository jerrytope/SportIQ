from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("institutions/", views.institutions, name="institutions"),
    path("demo/", views.demo, name="demo"),
    path("newsletter/", views.newsletter, name="newsletter"),
    path("blog/", views.blog, name="blog"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("events/", views.events, name="events"),
    path("p/<slug:slug>/", views.page, name="page"),
    path("offline/", views.offline, name="offline"),
]
