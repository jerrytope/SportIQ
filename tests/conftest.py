import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.assessments.models import Choice, Exam, Question, QuestionBank
from apps.catalog.models import Course, Lesson, Module, Profession, Track
from apps.credentials.models import CredentialType
from apps.institutions.models import Institution, Membership

PW = "Str0ng-pass-123"


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.PAYSTACK_SECRET_KEY = ""
    settings.REQUIRE_STAFF_2FA = False
    settings.STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"


def make_user(email, roles=None, **extra):
    u = User.objects.create_user(email=email, password=PW, first_name=email.split("@")[0].title(), last_name="Test",
                                 email_verified=True, **extra)
    if roles:
        u.staff_roles = roles
        u.save()
    return u


@pytest.fixture
def learner(db):
    return make_user("learner@example.com", state="Lagos")


@pytest.fixture
def coach_profession(db):
    return Profession.objects.create(name="Coach", plural="Coaches")


@pytest.fixture
def course(db):
    """Published free course: 2 reading lessons + a quiz lesson with a 3-question final exam (pass 60%)."""
    track = Track.objects.create(name="Integrity")
    ctype = CredentialType.objects.create(code="course-completion", name="Certificate of Completion", kind="completion",
                                          validity_months=24)
    c = Course.objects.create(title="Safeguarding Basics", summary="Keep children safe.", track=track,
                              status=Course.PUBLISHED, version=1, published_at=timezone.now(), credential_type=ctype)
    bank = QuestionBank.objects.create(course=c, title="Bank")
    for i in range(3):
        q = Question.objects.create(bank=bank, kind="mcq", text=f"Question {i}?", topic="Basics")
        Choice.objects.create(question=q, text="Right", is_correct=True)
        Choice.objects.create(question=q, text="Wrong")
    exam = Exam.objects.create(course=c, bank=bank, title="Final", is_final=True, is_published=True, question_count=3,
                               pass_mark=60)
    m = Module.objects.create(course=c, title="Module 1", order=1)
    Lesson.objects.create(module=m, title="Lesson A", kind="reading", body="Text", order=1)
    Lesson.objects.create(module=m, title="Lesson B", kind="reading", body="Text", order=2)
    Lesson.objects.create(module=m, title="Assessment", kind="quiz", exam=exam, order=3)
    return c


@pytest.fixture
def two_orgs(db):
    a = Institution.objects.create(name="Federation A", kind="federation")
    b = Institution.objects.create(name="Federation B", kind="federation")
    admin_a = make_user("admin-a@example.com")
    Membership.objects.create(user=admin_a, institution=a, role="admin")
    member_a = make_user("member-a@example.com")
    Membership.objects.create(user=member_a, institution=a)
    member_b = make_user("member-b@example.com")
    Membership.objects.create(user=member_b, institution=b)
    return {"a": a, "b": b, "admin_a": admin_a, "member_a": member_a, "member_b": member_b}
