import json
from unittest import mock

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.assessments.models import Appeal, Attempt, Question
from apps.credentials.models import CPDActivity, Credential, CredentialType, PriorLearningClaim, Programme
from apps.institutions.models import Institution, Membership
from apps.learning.models import Enrolment

from .conftest import make_user

pytestmark = pytest.mark.django_db


def pass_exam(client, user, course):
    exam = course.final_exam()
    client.post(reverse("learning:exam_start", args=[exam.pk]), {"declare": "on"})
    att = Attempt.objects.filter(user=user, exam=exam).latest("started_at")
    data = {f"q{r.question_id}": [c.pk for c in r.question.choices.filter(is_correct=True)] for r in att.responses.all()}
    client.post(reverse("learning:attempt", args=[att.pk]), data)
    att.refresh_from_db()
    return att


def complete_course(client, user, course):
    client.force_login(user)
    client.post(reverse("learning:enrol", args=[course.slug]))
    for l in course.lessons():
        if l.kind != "quiz":
            client.post(reverse("learning:complete", args=[course.slug, l.pk]))
    pass_exam(client, user, course)
    quiz = course.lessons().filter(kind="quiz").first()
    client.post(reverse("learning:complete", args=[course.slug, quiz.pk]))


# --- Qualifications, practicals, CPD ------------------------------------------------------------

def test_programme_awarded_after_courses_and_supervised_practical(client, learner, course):
    from apps.practicals.models import PracticalTask, Submission

    qual = CredentialType.objects.create(code="q1", name="Level 1", kind="qualification", validity_months=36)
    task = PracticalTask.objects.create(course=course, title="Observed session", instructions="Do it", requires_supervisor=True,
                                        rubric=[{"title": "Safety", "max": 5}])
    prog = Programme.objects.create(title="Level 1 Qualification", slug="l1", summary="x", credential_type=qual)
    prog.courses.add(course)
    prog.practical_tasks.add(task)
    complete_course(client, learner, course)
    assert not Credential.objects.filter(user=learner, credential_type=qual).exists()
    assert CPDActivity.objects.filter(user=learner, kind="course", status="approved").exists()  # automatic CPD

    client.post(reverse("practicals:task", args=[task.pk]), {"text": "Delivered to U-13s", "supervisor_name": "Coach A",
                                                             "supervisor_email": "a@example.com", "supervisor_role": "Level 2"})
    sub = Submission.objects.get(user=learner)
    instructor = make_user("ins@example.com", roles=["instructor"])
    client.force_login(instructor)
    client.post(reverse("backoffice:practical_assess", args=[sub.pk]), {"c0": "4", "feedback": "Good", "action": "assess"})
    sub.refresh_from_db()
    assert sub.status == "passed" and sub.awaiting_supervisor
    assert not Credential.objects.filter(user=learner, credential_type=qual).exists()  # still needs supervisor

    client.logout()
    page = client.get(reverse("practicals:signoff", args=[sub.supervisor_token]))
    assert page.status_code == 200
    client.post(reverse("practicals:signoff", args=[sub.supervisor_token]), {"decision": "confirm", "declare": "on"})
    assert Credential.objects.filter(user=learner, credential_type=qual, title="Level 1 Qualification").exists()


def test_cpd_approval_and_renewal(client, learner, course):
    from apps.credentials import services

    ctype = course.credential_type
    ctype.cpd_points_for_renewal = 3
    ctype.save()
    cred = services.issue(learner, ctype, course.title, course=course)
    old_expiry = cred.expires_at
    client.force_login(learner)
    client.post(reverse("credentials:cpd"), {"title": "Workshop", "kind": "event", "date": "2026-10-01", "hours": "4"})
    act = CPDActivity.objects.get(user=learner, title="Workshop")
    registrar = make_user("reg@example.com", roles=["registrar"])
    client.force_login(registrar)
    client.post(reverse("backoffice:registrar"), {"kind": "cpd", "id": act.pk, "decision": "approve", "points": "4"})
    client.force_login(learner)
    client.post(reverse("credentials:renew", args=[cred.pk]))
    rr = cred.renewal_requests.get()
    client.force_login(registrar)
    client.post(reverse("backoffice:registrar"), {"kind": "renewal", "id": rr.pk, "decision": "approve"})
    cred.refresh_from_db()
    assert cred.expires_at > old_expiry and cred.events.filter(action="renewed").exists()


def test_rpl_claim_recognised_issues_credential(client, learner, course):
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(learner)
    client.post(reverse("credentials:rpl", args=[course.slug]), {"statement": "I hold an equivalent federation certificate since 2019.",
                                                                  "evidence": SimpleUploadedFile("c.txt", b"proof")})
    claim = PriorLearningClaim.objects.get(user=learner)
    client.force_login(make_user("reg@example.com", roles=["registrar"]))
    client.post(reverse("backoffice:registrar"), {"kind": "rpl", "id": claim.pk, "decision": "approve", "note": "Verified"})
    assert Enrolment.objects.get(user=learner, course=course).status == "completed"
    assert Credential.objects.filter(user=learner, credential_type__code="rpl").exists()


def test_badge_json_is_open_badges(client, learner, course):
    from apps.credentials import services

    cred = services.issue(learner, course.credential_type, course.title, course=course)
    data = client.get(reverse("credentials:badge", args=[cred.pk])).json()
    assert "OpenBadgeCredential" in data["type"] and data["credentialSubject"]["name"]


# --- Assessment: appeals, moderation, similarity, schedule ------------------------------------------

def test_appeal_upheld_grants_extra_attempt(client, learner, course):
    exam = course.final_exam()
    exam.attempts_allowed = 1
    exam.save()
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    client.post(reverse("learning:exam_start", args=[exam.pk]), {"declare": "on"})
    att = Attempt.objects.get(user=learner)
    client.post(reverse("learning:attempt", args=[att.pk]), {})
    client.post(reverse("learning:exam_appeal", args=[exam.pk]), {"kind": "resit", "reason": "I was unwell during the exam."})
    appeal = Appeal.objects.get(user=learner)
    client.force_login(make_user("ins@example.com", roles=["instructor"]))
    client.post(reverse("backoffice:appeals"), {"appeal": appeal.pk, "decision": "uphold", "outcome": "Resit granted"})
    assert exam.allowed_attempts(learner) == 2
    client.force_login(learner)
    client.post(reverse("learning:exam_start", args=[exam.pk]), {"declare": "on"})
    assert Attempt.objects.filter(user=learner).count() == 2


def test_declaration_required_to_start(client, learner, course):
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    client.post(reverse("learning:exam_start", args=[course.final_exam().pk]))
    assert not Attempt.objects.filter(user=learner).exists()


def test_moderation_required_before_release_by_second_marker(client, learner, course):
    exam = course.final_exam()
    exam.requires_moderation = True
    exam.save()
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    att = pass_exam(client, learner, course)
    assert att.status == Attempt.MARKED
    first = make_user("m1@example.com", roles=["instructor"])
    client.force_login(first)
    client.post(reverse("backoffice:mark_attempt", args=[att.pk]), {"action": "release"})
    att.refresh_from_db()
    assert att.status == Attempt.MARKED  # blocked
    client.post(reverse("backoffice:moderate", args=[att.pk]), {"note": "checked"})
    client.post(reverse("backoffice:mark_attempt", args=[att.pk]), {"action": "release"})
    att.refresh_from_db()
    assert att.status == Attempt.RELEASED


def test_similarity_flag_on_copied_essay(client, course):
    from apps.assessments import services

    exam = course.final_exam()
    q = Question.objects.create(bank=exam.bank, kind="essay", text="Explain.", points=5)
    essay = " ".join(f"word{i}" for i in range(60))
    atts = []
    for i in range(2):
        u = make_user(f"s{i}@example.com")
        att = Attempt.objects.create(exam=exam, user=u, deadline=timezone.now() + timezone.timedelta(minutes=5))
        att.responses.create(question=q, text=essay)
        atts.append(att)
    assert services.check_similarity(atts[1]) >= 90
    atts[1].refresh_from_db()
    assert any("similar" in f for f in atts[1].integrity_flags)


def test_scheduled_exam_window(client, learner, course):
    exam = course.final_exam()
    exam.opens_at = timezone.now() + timezone.timedelta(days=1)
    exam.save()
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    client.post(reverse("learning:exam_start", args=[exam.pk]), {"declare": "on"})
    assert not Attempt.objects.exists()


# --- Live, library, labs ---------------------------------------------------------------------------

def test_live_join_records_attendance_and_cpd(client, learner, course):
    from apps.live.models import LiveSession, Registration

    host = make_user("host@example.com", roles=["instructor"])
    s = LiveSession.objects.create(title="Live", host=host, course=course, starts_at=timezone.now(), is_public=True)
    client.force_login(learner)
    client.post(reverse("live:join", args=[s.pk]))
    assert Registration.objects.get(session=s, user=learner).attended
    assert CPDActivity.objects.filter(user=learner, kind="live").exists()


def test_library_restricted_items_hidden(client, learner):
    from apps.library.models import Resource

    Resource.objects.create(title="Secret governance draft", kind="legal", access_level="restricted")
    Resource.objects.create(title="Open rules", kind="rules", access_level="public")
    client.force_login(learner)
    page = client.get(reverse("library:index")).content
    assert b"Open rules" in page and b"Secret governance" not in page
    r = Resource.objects.get(title__startswith="Secret")
    assert client.get(r.get_absolute_url()).status_code == 404


def test_lab_engines_score():
    from apps.labs import engines
    from apps.labs.models import Run, Scenario

    s = Scenario(engine="branching", data={"start": "a", "nodes": {"a": {"text": "x", "options": [{"text": "good", "score": 10, "next": None}]}}})
    run = Run(path=[])
    engines.branching_step(s, run, 0)
    assert run.completed and run.score == 100
    load = Scenario(engine="load", data={"threshold": 1.5, "athletes": [{"name": "A", "weeks": [100, 100, 100, 100, 200]},
                                                                         {"name": "B", "weeks": [100, 100, 100, 100, 100]}]})
    assert engines.score_load(load, ["A"])[0] == 100
    designer = Scenario(data={"target_minutes": 30, "drills": [{"id": "w", "phase": "warmup", "minutes": 10}, {"id": "s", "phase": "skill", "minutes": 10},
                                                                {"id": "g", "phase": "game", "minutes": 5}, {"id": "c", "phase": "cooldown", "minutes": 5}]})
    assert engines.score_designer(designer, ["w", "s", "g", "c"])[0] == 100
    assert engines.score_designer(designer, ["g", "w"])[0] < 60
    budget = Scenario(data={"total": 100, "lines": [{"key": "med", "label": "Medical", "min": 30}]})
    assert engines.score_budget(budget, {"med": 10})[0] < engines.score_budget(budget, {"med": 95})[0]


def test_medical_lab_restricted_to_verified(client, learner):
    from apps.labs.models import Scenario

    s = Scenario.objects.create(title="Concussion", kind="medicine", summary="x", requires_qualified=True,
                                data={"start": "a", "nodes": {"a": {"text": "x", "options": []}}})
    client.force_login(learner)
    assert client.get(s.get_absolute_url()).status_code == 403


# --- AI ------------------------------------------------------------------------------------------------

def test_ai_answers_with_citations_from_approved_content(client, learner, course, settings):
    settings.AI_PROVIDER = ""
    from apps.ai import services

    lesson = course.lessons().first()
    lesson.body = "Strict liability means the athlete is responsible for any prohibited substance found in their sample."
    lesson.save()
    services.rebuild_index()
    result = services.answer(learner, "what does strict liability mean")
    assert result["citations"] and "Strict liability" in result["content"]


def test_ai_blocked_during_exam_and_refuses_exam_items(client, learner, course):
    from apps.ai import services

    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    q = course.final_exam().bank.questions.first()
    q.text = "Which statement about the safeguarding duty of care for youth football coaches is correct?"
    q.save()
    assert services.answer(learner, "Which statement about the safeguarding duty of care for youth football coaches is correct?")["refused"]
    assert not services.answer(learner, "what is duty of care")["refused"]  # concept questions are allowed
    client.post(reverse("learning:exam_start", args=[course.final_exam().pk]), {"declare": "on"})
    assert "switched off" in services.answer(learner, "anything at all")["content"]


def test_ai_uses_claude_with_fallbacks_when_key_set(learner, course, settings):
    settings.AI_PROVIDER, settings.ANTHROPIC_API_KEY = "anthropic", "test-key"
    from apps.ai import services

    lesson = course.lessons().first()
    lesson.body = "Progressive overload means gradually increasing training stress over weeks."
    lesson.save()
    services.rebuild_index()
    fake = mock.MagicMock()
    fake.stop_reason = "end_turn"
    fake.model = "claude-opus-5-5"
    fake.content = [mock.MagicMock(type="text", text="It means increasing load gradually [1].")]
    with mock.patch("anthropic.Anthropic") as client_cls:
        client_cls.return_value.beta.messages.create.return_value = fake
        result = services.answer(learner, "what is progressive overload")
        kwargs = client_cls.return_value.beta.messages.create.call_args.kwargs
    assert result["content"].startswith("It means") and result["engine"] == "claude-opus-5-5"
    assert kwargs["model"] == "claude-opus-5-5" and kwargs["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in kwargs["betas"] and "SOURCES" in kwargs["messages"][-1]["content"]


def test_copilot_drafts_are_inactive_until_approved(client, course, settings):
    settings.AI_PROVIDER = ""
    from apps.ai import services

    text = ("Safeguarding protects children in sport. Coaches must report concerns to the designated safeguarding officer immediately. "
            "Never promise to keep a disclosure secret from the safeguarding officer. Record the exact words used by the child promptly.")
    drafts = services.draft_questions(course, text, n=2)
    assert drafts and all(q.ai_draft and not q.is_active for q in drafts)
    assert not any(q in course.final_exam().draw_questions() for q in drafts)


# --- Community, workforce, research, integrity ----------------------------------------------------------

def test_private_group_and_reporting(client, learner):
    from apps.community.models import ContentReport, Discussion, Group, GroupMember

    g = Group.objects.create(name="Private", is_private=True)
    client.force_login(learner)
    client.post(reverse("community:join", args=[g.slug]))
    assert not GroupMember.objects.get(group=g, user=learner).approved
    open_g = Group.objects.create(name="Open")
    d = Discussion.objects.create(group=open_g, author=learner, title="t", body="b")
    client.post(reverse("community:report", args=["discussion", d.pk]), {"reason": "spam"})
    assert ContentReport.objects.filter(object_id=d.pk).exists()


def test_pending_opportunity_not_public(client):
    from apps.community.models import Opportunity

    o = Opportunity.objects.create(kind="job", title="Pending job", organisation="X", description="y", status="pending")
    assert client.get(o.get_absolute_url()).status_code == 404
    assert b"Pending job" not in client.get(reverse("community:opportunities")).content


def test_workforce_search_authorisation_and_consent(client, learner):
    from apps.workforce.models import DirectorySearch, WorkforceProfile

    client.force_login(learner)
    assert client.get(reverse("workforce:search")).status_code == 403
    listed = make_user("listed@example.com", state="Kano")
    WorkforceProfile.objects.create(user=listed, listed=True)
    make_user("hidden@example.com", state="Kano")
    fed = Institution.objects.create(name="Fed", kind="federation")
    admin = make_user("fedadmin@example.com")
    Membership.objects.create(user=admin, institution=fed, role="admin")
    client.force_login(admin)
    page = client.get(reverse("workforce:search"), {"state": "Kano"}).content
    assert b"Listed" in page and b"hidden@example.com" not in page and b"Hidden" not in page
    assert DirectorySearch.objects.filter(searched_by=admin).exists()


def test_skills_map_suppresses_small_counts():
    from apps.workforce import services

    make_user("one@example.com", state="Kano")
    cells, *_ = services.skills_map()
    kano = next(c for c in cells if c["state"] == "Kano")
    assert kano["total"] is None


def test_restricted_dataset_needs_approval(client, learner):
    from django.core.files.base import ContentFile

    from apps.research.models import Dataset, DatasetRequest

    d = Dataset.objects.create(title="Injuries", description="x", access="approval", file=ContentFile(b"a,b\n", name="d.csv"))
    client.force_login(learner)
    assert client.get(reverse("research:dataset_download", args=[d.pk])).status_code == 404
    client.post(reverse("research:dataset_request", args=[d.pk]), {"purpose": "Teaching a data literacy module", "agree": "on"})
    req = DatasetRequest.objects.get(user=learner)
    client.force_login(make_user("ro@example.com", roles=["research_officer"]))
    client.post(reverse("backoffice:research_office"), {"kind": "dataset", "id": req.pk, "decision": "approve"})
    client.force_login(learner)
    assert client.get(reverse("research:dataset_download", args=[d.pk])).status_code == 200


def test_integrity_report_encrypted_and_restricted(client):
    from apps.integrity.models import Report

    client.post(reverse("integrity:report"), {"category": "safeguarding", "description": "A coach is texting a 12-year-old at night.",
                                              "anonymous": "on", "state": ""})
    r = Report.objects.get()
    with connection.cursor() as cur:
        cur.execute("SELECT description FROM integrity_report WHERE id = %s", [r.pk])
        raw = cur.fetchone()[0]
    assert raw.startswith("enc::") and "texting" not in raw
    assert r.description.startswith("A coach")
    admin = make_user("super@example.com", roles=["super_admin"])
    client.force_login(admin)
    assert client.get(reverse("integrity:case", args=[r.pk])).status_code == 403
    officer = make_user("so@example.com", roles=["safeguarding_officer"])
    client.force_login(officer)
    assert client.get(reverse("integrity:case", args=[r.pk])).status_code == 200
    client.logout()
    status = client.post(reverse("integrity:status"), {"reference": r.reference, "code": r.access_code})
    assert b"being handled" in status.content or r.get_status_display().encode() in status.content


# --- Integrations, i18n, observatory ----------------------------------------------------------------

def test_api_key_scopes_and_xapi(client, learner):
    from apps.integrations.models import ApiKey, XAPIStatement

    inst = Institution.objects.create(name="Fed X", kind="federation")
    Membership.objects.create(user=learner, institution=inst)
    key, raw = ApiKey.generate(name="k", scopes=["xapi:write"], institution=inst)
    stmt = {"actor": {"mbox": f"mailto:{learner.email}"}, "verb": {"id": "http://adlnet.gov/expapi/verbs/completed"},
            "object": {"id": "https://example.org/activity/1"}}
    r = client.post("/xapi/statements", data=json.dumps(stmt), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert r.status_code == 200 and XAPIStatement.objects.get().user == learner
    assert client.get("/api/v1/institution/credentials/", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code == 401  # missing scope
    key.scopes = ["credentials:read"]
    key.save()
    assert client.get("/api/v1/institution/credentials/", HTTP_AUTHORIZATION=f"Bearer {raw}").json()["institution"] == "Fed X"
    assert client.get("/api/v1/institution/credentials/", HTTP_AUTHORIZATION="Bearer siq_bad.key").status_code == 401


def test_scorm_package_completes_lesson(client, learner, course, tmp_path, settings):
    import io
    import zipfile

    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MEDIA_ROOT = tmp_path
    lesson = course.lessons().first()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("imsmanifest.xml", '<manifest xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"><organizations><organization>'
                                      '<title>Demo</title></organization></organizations><resources><resource href="index.html"/></resources></manifest>')
        z.writestr("index.html", "<html>hi</html>")
    client.force_login(make_user("cr@example.com", roles=["academic_manager"]))
    client.post(reverse("backoffice:scorm_upload", args=[lesson.pk]), {"package": SimpleUploadedFile("p.zip", buf.getvalue())})
    lesson.refresh_from_db()
    assert lesson.kind == "scorm" and lesson.scorm.launch_path == "index.html"
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    assert client.get(reverse("integrations:scorm_launch", args=[lesson.pk])).status_code == 200
    r = client.post(reverse("integrations:scorm_commit", args=[lesson.pk]), data=json.dumps({"cmi.core.lesson_status": "completed"}),
                    content_type="application/json")
    assert r.json()["completed"]
    assert Enrolment.objects.get(user=learner).lesson_progress.filter(lesson=lesson, completed=True).exists()


def test_webhook_emitted_on_credential(learner, course, django_capture_on_commit_callbacks):
    from apps.credentials import services
    from apps.integrations.models import Webhook, WebhookDelivery

    Webhook.objects.create(url="https://example.org/hook", events=["credential.issued"])
    resp = mock.MagicMock()
    resp.__enter__.return_value.status = 200
    with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen, django_capture_on_commit_callbacks(execute=True):
        services.issue(learner, course.credential_type, course.title, course=course)
    req = urlopen.call_args.args[0]
    assert req.headers["X-sportiq-signature"].startswith("sha256=")
    assert WebhookDelivery.objects.get().status_code == 200


def test_language_switch_translates_navigation(client, learner):
    client.force_login(learner)
    client.post("/i18n/setlang/", {"language": "yo", "next": "/learn/"})
    page = client.get("/learn/").content.decode()
    assert "Ẹ̀kọ́ mi" in page  # "My learning" in Yoruba


def test_approved_translation_shown(client, learner, course):
    from apps.catalog.models import CourseTranslation

    CourseTranslation.objects.create(course=course, language="pcm", title="Safeguarding (Pidgin)", summary="s", status="approved")
    client.force_login(learner)
    client.post("/i18n/setlang/", {"language": "pcm", "next": "/"})
    assert b"Safeguarding (Pidgin)" in client.get(course.get_absolute_url()).content


def test_observatory_and_identity_sandbox(client, learner, settings):
    assert client.get(reverse("observatory")).status_code == 200
    settings.IDENTITY_VERIFICATION_ENABLED = True
    client.force_login(learner)
    r = client.post(reverse("verify_identity"), {"id_number": "12345678902"}, follow=True)
    assert b"Identity confirmed" in r.content
    from apps.integrations.models import RegistryAdapterLog

    assert RegistryAdapterLog.objects.get().request_summary.endswith("902")


def test_challenge_progress(client, learner, course):
    from apps.careers.models import Challenge

    c = Challenge.objects.create(title="Sprint", metric="lessons", target=2, starts_on=timezone.localdate(), ends_on=timezone.localdate())
    client.force_login(learner)
    client.post(reverse("careers:join_challenge", args=[c.pk]))
    client.post(reverse("learning:enrol", args=[course.slug]))
    for l in course.lessons()[:2]:
        client.post(reverse("learning:complete", args=[course.slug, l.pk]))
    assert b"2 of 2" in client.get(reverse("careers:challenge", args=[c.pk])).content


def test_cv_and_portfolio_pdfs(client, learner):
    client.force_login(learner)
    assert client.get(reverse("careers:cv"))["Content-Type"] == "application/pdf"
    assert client.get(reverse("credentials:portfolio"))["Content-Type"] == "application/pdf"


@pytest.mark.parametrize("url", ["/library/", "/community/opportunities/", "/integrity/report/", "/observatory/", "/lti/jwks.json"])
def test_new_public_pages(client, url):
    assert client.get(url).status_code == 200


def test_ai_uses_openai_when_configured(learner, course, settings):
    settings.AI_PROVIDER, settings.OPENAI_API_KEY, settings.OPENAI_MODEL = "openai", "sk-test", "gpt-test"
    from apps.ai import services

    lesson = course.lessons().first()
    lesson.body = "Progressive overload means gradually increasing training stress over weeks."
    lesson.save()
    services.rebuild_index()
    fake = mock.MagicMock()
    fake.model = "gpt-test"
    fake.choices = [mock.MagicMock(finish_reason="stop", message=mock.MagicMock(content="Increase load gradually [1].", refusal=None))]
    with mock.patch("openai.OpenAI") as client_cls:
        client_cls.return_value.chat.completions.create.return_value = fake
        result = services.answer(learner, "what is progressive overload")
        kwargs = client_cls.return_value.chat.completions.create.call_args.kwargs
    assert result["content"] == "Increase load gradually [1]." and result["engine"] == "gpt-test" and result["citations"]
    assert kwargs["model"] == "gpt-test" and kwargs["messages"][0]["role"] == "system"
    assert "SOURCES" in kwargs["messages"][-1]["content"]


def test_openai_failure_falls_back_to_quoted_passages(learner, course, settings):
    import openai

    settings.AI_PROVIDER, settings.OPENAI_API_KEY = "openai", "sk-test"
    from apps.ai import services

    lesson = course.lessons().first()
    lesson.body = "Hydration in the heat means drinking before, during and after training."
    lesson.save()
    services.rebuild_index()
    with mock.patch("openai.OpenAI") as client_cls:
        client_cls.return_value.chat.completions.create.side_effect = openai.APIConnectionError(request=mock.MagicMock())
        result = services.answer(learner, "hydration in the heat")
    assert result["engine"] == "retrieval" and "approved SportIQ material" in result["content"]
