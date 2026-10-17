from django.urls import path

from . import views
from .views import phase2

app_name = "backoffice"

urlpatterns = [
    path("", views.home, name="home"),
    path("analytics/", views.analytics, name="analytics"),
    path("analytics/export.csv", views.analytics_export, name="analytics_export"),
    # Academic
    path("studio/", views.studio, name="studio"),
    path("studio/new/", views.course_create, name="course_create"),
    path("studio/<int:pk>/", views.course_builder, name="course_builder"),
    path("studio/<int:pk>/settings/", views.course_edit, name="course_edit"),
    path("studio/<int:pk>/workflow/", views.course_workflow, name="course_workflow"),
    path("studio/<int:pk>/modules/add/", views.module_add, name="module_add"),
    path("studio/modules/<int:pk>/", views.module_edit, name="module_edit"),
    path("studio/modules/<int:module_id>/lessons/add/", views.lesson_edit, name="lesson_add"),
    path("studio/lessons/<int:pk>/", views.lesson_edit, name="lesson_edit"),
    path("studio/lessons/<int:pk>/delete/", views.lesson_delete, name="lesson_delete"),
    path("studio/<int:pk>/questions/", views.question_bank, name="question_bank"),
    path("studio/questions/<int:pk>/", views.question_edit, name="question_edit"),
    path("studio/<int:pk>/exam/", views.exam_edit, name="exam_edit"),
    path("reviews/", views.review_queue, name="review_queue"),
    path("assessments/", views.marking, name="marking"),
    path("assessments/attempts/<int:pk>/", views.mark_attempt, name="mark_attempt"),
    path("assessments/exams/<int:pk>/analysis/", views.item_analysis, name="item_analysis"),
    path("admissions/", views.admissions, name="admissions"),
    path("admissions/<int:pk>/", views.admission_decide, name="admission_decide"),
    path("cohorts/", views.cohorts, name="cohorts"),
    path("cohorts/<int:pk>/", views.cohort_detail, name="cohort_detail"),
    path("academic/", views.academic, name="academic"),
    # Credentials
    path("credentials/", views.credentials, name="credentials"),
    path("credentials/issue/", views.credential_issue, name="credential_issue"),
    path("credentials/<uuid:pk>/", views.credential_manage, name="credential_manage"),
    # People
    path("users/", views.users, name="users"),
    path("users/import/", views.users_import, name="users_import"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("institutions/", views.institutions, name="institutions"),
    path("institutions/<int:pk>/", views.institution_edit, name="institution_edit"),
    path("org/<slug:slug>/", views.org, name="org"),
    path("org/<slug:slug>/members/<int:user_id>/", views.org_member, name="org_member"),
    # Finance
    path("finance/", views.finance, name="finance"),
    path("finance/orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("finance/vouchers/", views.vouchers, name="vouchers"),
    path("finance/export.csv", views.finance_export, name="finance_export"),
    # Engagement
    path("support/", views.tickets, name="tickets"),
    path("support/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("support/articles/", views.help_articles, name="help_articles"),
    path("support/articles/<int:pk>/", views.help_article_edit, name="help_article_edit"),
    path("support/notices/", views.status_notices, name="status_notices"),
    path("comms/", views.comms, name="comms"),
    path("site/", views.site_content, name="site"),
    path("site/<str:kind>/", views.site_list, name="site_list"),
    path("site/<str:kind>/<int:pk>/", views.site_edit, name="site_edit"),
    # System
    path("settings/", views.settings_view, name="settings"),
    path("audit/", views.audit_log, name="audit"),
    path("privacy/", views.data_requests, name="data_requests"),
    # Phases 2-4
    path("records/<str:key>/", phase2.records, name="records"),
    path("records/<str:key>/new/", phase2.record_edit, name="record_new"),
    path("records/<str:key>/<int:pk>/", phase2.record_edit, name="record_edit"),
    path("live/<int:pk>/attendance/", phase2.mark_attendance, name="mark_attendance"),
    path("practicals/", phase2.practicals_queue, name="practicals"),
    path("practicals/<int:pk>/", phase2.practical_assess, name="practical_assess"),
    path("assessments/appeals/", phase2.appeals, name="appeals"),
    path("assessments/attempts/<int:pk>/moderate/", phase2.moderate, name="moderate"),
    path("registrar/", phase2.registrar, name="registrar"),
    path("moderation/", phase2.moderation, name="moderation"),
    path("research/", phase2.research_office, name="research_office"),
    path("studio/lessons/<int:lesson_id>/scorm/", phase2.scorm_upload, name="scorm_upload"),
    path("studio/<int:pk>/copilot/", phase2.copilot, name="copilot"),
    path("ai/", phase2.ai_centre, name="ai_centre"),
    path("integrations/", phase2.integrations, name="integrations"),
    path("integrations/export.zip", phase2.data_export, name="data_export"),
    path("impact/", phase2.impact, name="impact"),
]
