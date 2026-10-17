from datetime import datetime

import pytest
from django.urls import reverse

from apps.assessments.models import Attempt, Exam, Question
from apps.core.models import add_months
from apps.credentials.models import Credential
from apps.learning.models import Enrolment

pytestmark = pytest.mark.django_db


def answer_all_correct(client, attempt):
    data = {}
    for r in attempt.responses.select_related("question"):
        data[f"q{r.question_id}"] = [c.pk for c in r.question.choices.filter(is_correct=True)]
    return client.post(reverse("learning:attempt", args=[attempt.pk]), data)


def test_full_journey_enrol_learn_pass_certificate_verify(client, learner, course):
    client.force_login(learner)
    assert client.post(reverse("learning:enrol", args=[course.slug])).status_code == 302
    enrolment = Enrolment.objects.get(user=learner, course=course)
    lessons = list(course.lessons())
    for lesson in lessons[:2]:
        client.post(reverse("learning:complete", args=[course.slug, lesson.pk]))
    # Quiz lesson can't be completed before the exam is passed
    client.post(reverse("learning:complete", args=[course.slug, lessons[2].pk]))
    enrolment.refresh_from_db()
    assert enrolment.status == "active"

    exam = course.final_exam()
    client.post(reverse("learning:exam_start", args=[exam.pk]), {"declare": "on"})
    attempt = Attempt.objects.get(user=learner, exam=exam)
    answer_all_correct(client, attempt)
    attempt.refresh_from_db()
    assert attempt.status == Attempt.RELEASED and attempt.passed and attempt.percent == 100

    client.post(reverse("learning:complete", args=[course.slug, lessons[2].pk]))
    enrolment.refresh_from_db()
    assert enrolment.status == "completed" and enrolment.progress == 100

    cred = Credential.objects.get(user=learner, course=course)
    assert cred.is_valid and cred.grade == "100.0%"
    pdf = client.get(reverse("credentials:pdf", args=[cred.pk]))
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"

    client.logout()
    page = client.get(reverse("credentials:verify_code", args=[cred.code]))
    assert b"Valid credential" in page.content and b"not a professional licence" in page.content


def test_failed_attempt_and_attempt_limit(client, learner, course):
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    exam = course.final_exam()
    exam.attempts_allowed = 1
    exam.save()
    client.post(reverse("learning:exam_start", args=[exam.pk]), {"declare": "on"})
    attempt = Attempt.objects.get(user=learner)
    client.post(reverse("learning:attempt", args=[attempt.pk]), {})  # submits with no answers
    attempt.refresh_from_db()
    assert attempt.passed is False and attempt.status == Attempt.RELEASED
    client.post(reverse("learning:exam_start", args=[exam.pk]), {"declare": "on"})
    assert Attempt.objects.filter(user=learner).count() == 1  # no second attempt allowed


def test_essay_answers_wait_for_examiner_release(client, learner, course):
    from tests.conftest import make_user

    exam = course.final_exam()
    Question.objects.create(bank=exam.bank, kind="essay", text="Explain.", points=4)
    exam.question_count = 4
    exam.save()
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    client.post(reverse("learning:exam_start", args=[exam.pk]), {"declare": "on"})
    attempt = Attempt.objects.get(user=learner)
    answer_all_correct(client, attempt)
    attempt.refresh_from_db()
    assert attempt.status == Attempt.SUBMITTED

    examiner = make_user("examiner@example.com", roles=["instructor"])
    client.force_login(examiner)
    essay = attempt.responses.get(question__kind="essay")
    client.post(reverse("backoffice:mark_attempt", args=[attempt.pk]), {f"score_{essay.pk}": "3", f"feedback_{essay.pk}": "Good"})
    attempt.refresh_from_db()
    assert attempt.status == Attempt.MARKED  # not released automatically
    client.post(reverse("backoffice:mark_attempt", args=[attempt.pk]), {"action": "release"})
    attempt.refresh_from_db()
    assert attempt.status == Attempt.RELEASED and attempt.passed


def test_prerequisite_blocks_enrolment(client, learner, course):
    from apps.catalog.models import Course

    advanced = Course.objects.create(title="Advanced", summary="x", track=course.track, status=Course.PUBLISHED)
    advanced.prerequisites.add(course)
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[advanced.slug]))
    assert not Enrolment.objects.filter(user=learner, course=advanced).exists()


def test_unpublished_course_hidden_from_learners(client, learner, course):
    course.status = "draft"
    course.save()
    client.force_login(learner)
    assert client.get(course.get_absolute_url()).status_code == 404
    assert client.get(reverse("catalog:list")).content.count(b"Safeguarding Basics") == 0


def test_add_months_keeps_calendar_day():
    assert add_months(datetime(2026, 10, 15), 24) == datetime(2028, 10, 15)
    assert add_months(datetime(2026, 1, 31), 1) == datetime(2026, 2, 28)


def test_exam_question_draw_respects_blueprint(course):
    exam = Exam.objects.get(course=course)
    exam.blueprint = {"Basics": 2}
    exam.question_count = 2
    drawn = exam.draw_questions()
    assert len(drawn) == 2 and all(q.topic == "Basics" for q in drawn)
