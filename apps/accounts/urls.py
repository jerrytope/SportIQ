from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),
    path("verify-resend/", views.resend_verification, name="resend_verification"),
    path("profile/", views.profile, name="profile"),
    path("settings/", views.settings_view, name="settings"),
    path("payments/", views.payments, name="payments"),
    path("privacy/request/", views.data_request, name="data_request"),
    path("privacy/export/", views.export_data, name="export_data"),
    path("2fa/setup/", views.two_factor_setup, name="two_factor_setup"),
    path("2fa/verify/", views.two_factor_verify, name="two_factor_verify"),
    path("2fa/disable/", views.two_factor_disable, name="two_factor_disable"),
    path("password-reset/", views.password_reset, name="password_reset"),
    path("password-reset/sent/", views.password_reset_done, name="password_reset_done"),
    path("reset/<uidb64>/<token>/", views.password_reset_confirm, name="password_reset_confirm"),
    path("reset/done/", views.password_reset_complete, name="password_reset_complete"),
]
