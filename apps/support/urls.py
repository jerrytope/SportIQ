from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("", views.help_centre, name="help"),
    path("faqs/", views.faqs, name="faqs"),
    path("tickets/", views.my_tickets, name="my_tickets"),
    path("tickets/<int:pk>/", views.ticket, name="ticket"),
    path("articles/<slug:slug>/", views.article, name="article"),
]
