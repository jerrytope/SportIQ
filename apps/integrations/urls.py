from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("scorm/<int:lesson_id>/launch/", views.scorm_launch, name="scorm_launch"),
    path("scorm/<int:lesson_id>/commit/", views.scorm_commit, name="scorm_commit"),
    path("xapi/statements", views.xapi_statements, name="xapi_statements"),
    path("api/v1/institution/credentials/", views.api_members_credentials, name="api_members_credentials"),
    path("api/v1/institution/enrolments/", views.api_members_enrolments, name="api_members_enrolments"),
    path("lti/login/", views.lti_login, name="lti_login"),
    path("lti/launch/", views.lti_launch, name="lti_launch"),
    path("lti/jwks.json", views.lti_jwks, name="lti_jwks"),
    path("sso/start/", views.sso_start, name="sso_start"),
    path("sso/callback/", views.sso_callback, name="sso_callback"),
]
