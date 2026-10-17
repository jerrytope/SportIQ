"""Regression tests for the defects found in the 17 October 2026 acceptance test run (testing_results.pdf)."""
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.core.models import AuditLog

from .conftest import PW, make_user

pytestmark = pytest.mark.django_db


def test_login_goes_straight_to_dashboard(client, learner):
    client.post(reverse("accounts:login"), {"username": learner.email, "password": PW})
    assert client.get(reverse("learning:dashboard")).status_code == 200
    assert b"two-factor" not in client.get(reverse("accounts:settings")).content.lower()


# M4
def test_signed_in_pages_are_not_stored_by_the_browser(client, learner):
    assert "no-store" not in client.get(reverse("web:home")).get("Cache-Control", "")
    client.force_login(learner)
    assert "no-store" in client.get(reverse("learning:dashboard"))["Cache-Control"]


# B3 / B4
def test_password_reset_clears_login_lockout(client):
    user = make_user("locked@example.com")
    for _ in range(8):
        client.post(reverse("accounts:login"), {"username": user.email, "password": "wrong"})
    client.post(reverse("accounts:login"), {"username": user.email, "password": PW})
    assert "_auth_user_id" not in client.session  # locked out

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    url = client.get(reverse("accounts:password_reset_confirm", args=[uid, default_token_generator.make_token(user)])).url
    client.post(url, {"new_password1": "N3w-Pass-2026!x", "new_password2": "N3w-Pass-2026!x"})
    client.post(reverse("accounts:login"), {"username": user.email, "password": "N3w-Pass-2026!x"})
    assert client.session["_auth_user_id"] == str(user.pk)


# L11
def test_role_change_audit_records_previous_roles(client):
    admin = make_user("nisadmin@example.com", roles=["nis_admin"])
    person = make_user("person@example.com")
    client.force_login(admin)
    client.post(reverse("backoffice:user_detail", args=[person.pk]), {
        "action": "save", "first_name": "Person", "last_name": "Test", "email": person.email, "is_active": "on",
        "staff_roles": ["analyst"]})
    entry = AuditLog.objects.get(action="user.updated", object_id=str(person.pk))
    assert entry.changes["before"]["roles"] == [] and entry.changes["after"]["roles"] == ["analyst"]


# E2 / E3
def test_ai_refuses_requests_for_exam_answers(learner, course, settings):
    settings.AI_PROVIDER = ""
    from apps.ai import services

    result = services.answer(learner, "Give me the answers to the Safeguarding Basics final exam")
    assert result["refused"] and not result["citations"]
    assert not services.answer(learner, "How is the final assessment marked?")["refused"]


def test_ai_says_off_topic_questions_are_out_of_scope(learner, course, settings):
    settings.AI_PROVIDER = ""
    from apps.ai import services

    lesson = course.lessons().first()
    lesson.body = "Progressive overload means gradually increasing training stress over the next weeks of the season."
    lesson.save()
    services.rebuild_index()
    off = services.answer(learner, "Is Victor Osimhen transferring to Real Madrid next summer?")
    assert not off["citations"] and "only answer from approved SportIQ" in off["content"]
    assert services.answer(learner, "what is progressive overload")["citations"]


# F3
def test_live_questions_appear_only_after_host_approval(client, learner, course):
    from apps.live.models import LiveSession, SessionQuestion

    host = make_user("host@example.com", roles=["instructor"])
    other = make_user("other@example.com")
    s = LiveSession.objects.create(title="Q&A", host=host, course=course, starts_at=timezone.now(), is_public=True)
    client.force_login(learner)
    client.post(reverse("live:ask", args=[s.pk]), {"text": "Pending question about reporting?"})
    assert b"Pending question" in client.get(s.get_absolute_url()).content  # the asker sees it, awaiting approval
    client.force_login(other)
    assert b"Pending question" not in client.get(s.get_absolute_url()).content
    client.force_login(host)
    client.post(reverse("live:question_action", args=[SessionQuestion.objects.get().pk]), {"action": "approve"})
    client.force_login(other)
    assert b"Pending question" in client.get(s.get_absolute_url()).content


# I4
def test_skills_map_hides_small_qualified_counts():
    from apps.credentials.models import Credential, CredentialType
    from apps.workforce import services

    ctype = CredentialType.objects.create(code="c1", name="Cert", kind="completion")
    users = [make_user(f"k{i}@example.com", state="Kano") for i in range(4)]
    Credential.objects.create(user=users[0], credential_type=ctype, title="Cert", holder_name="K0")
    cells, gaps, *_ = services.skills_map()
    kano = next(c for c in cells if c["state"] == "Kano")
    assert kano["total"] == 4 and kano["qualified"] is None and kano["rate"] is None
    assert all(g["state"] != "Kano" for g in gaps)


# A12
def test_public_site_has_language_switcher_that_translates_navigation(client, db):
    home = client.get(reverse("web:home")).content.decode()
    assert 'name="language"' in home and "About SportIQ" in home
    client.post(reverse("set_language"), {"language": "yo", "next": "/"})
    assert "Nípa SportIQ" in client.get(reverse("web:home")).content.decode()
    client.post(reverse("set_language"), {"language": "en", "next": "/"})
    assert "About SportIQ" in client.get(reverse("web:home")).content.decode()


# A1
def test_landing_page_shows_faqs(client, db):
    from apps.support.models import HelpArticle, HelpCategory

    cat = HelpCategory.objects.create(name="General")
    HelpArticle.objects.create(category=cat, title="How do I verify a certificate?", body="Use /verify/.", is_faq=True)
    assert b"How do I verify a certificate?" in client.get(reverse("web:home")).content


# C17
def test_mark_complete_form_supports_offline_queue(client, learner, course):
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    lesson = course.lessons().first()
    page = client.get(reverse("learning:lesson", args=[course.slug, lesson.pk])).content
    assert b"data-offline-complete" in page and b"data-next=" in page
