from django.urls import path

from . import views

app_name = "commerce"

urlpatterns = [
    path("checkout/<slug:slug>/", views.checkout, name="checkout"),
    path("pay/test/<str:reference>/", views.test_gateway, name="test_gateway"),
    path("pay/callback/", views.callback, name="callback"),
    path("pay/webhook/paystack/", views.webhook, name="webhook"),
    path("receipts/<str:reference>.pdf", views.receipt, name="receipt"),
]
