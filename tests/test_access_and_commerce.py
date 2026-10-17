import pytest
from django.urls import reverse

from apps.accounts.models import Consent, User
from apps.catalog.models import Course
from apps.commerce.models import Order, Voucher
from apps.core.models import AuditLog
from apps.credentials import services as cred_services
from apps.learning.models import Enrolment

from .conftest import PW, make_user

pytestmark = pytest.mark.django_db


# --- Access control -----------------------------------------------------------------------

def test_learner_cannot_open_back_office(client, learner):
    client.force_login(learner)
    assert client.get(reverse("backoffice:home")).status_code == 403
    assert client.get(reverse("backoffice:users")).status_code == 403


def test_role_scoping_in_back_office(client):
    finance = make_user("fin@example.com", roles=["finance_officer"])
    client.force_login(finance)
    assert client.get(reverse("backoffice:finance")).status_code == 200
    assert client.get(reverse("backoffice:users")).status_code == 403
    assert client.get(reverse("backoffice:credentials")).status_code == 403


def test_institution_admin_sees_only_own_members(client, two_orgs):
    client.force_login(two_orgs["admin_a"])
    a, b = two_orgs["a"], two_orgs["b"]
    page = client.get(reverse("backoffice:org", args=[a.slug]))
    assert page.status_code == 200
    assert two_orgs["member_a"].first_name.encode() in page.content
    assert two_orgs["member_b"].email.encode() not in page.content
    assert client.get(reverse("backoffice:org", args=[b.slug])).status_code == 404
    assert client.get(reverse("backoffice:org_member", args=[a.slug, two_orgs["member_b"].pk])).status_code == 404
    assert client.get(reverse("backoffice:org_member", args=[a.slug, two_orgs["member_a"].pk])).status_code == 200
    assert AuditLog.objects.filter(action="org.member_viewed").exists()


def test_creator_cannot_approve_own_course(client, course):
    creator = make_user("creator@example.com", roles=["course_creator", "reviewer"])
    course.owner = creator
    course.status = Course.IN_REVIEW
    course.save()
    client.force_login(creator)
    client.post(reverse("backoffice:course_workflow", args=[course.pk]), {"action": "approve"})
    course.refresh_from_db()
    assert course.status == Course.IN_REVIEW


def test_review_and_publish_workflow_bumps_version(client, course):
    creator = make_user("creator@example.com", roles=["course_creator"])
    reviewer = make_user("rev@example.com", roles=["reviewer"])
    manager = make_user("am@example.com", roles=["academic_manager"])
    course.status, course.owner, course.version = Course.DRAFT, creator, 1
    course.objectives = course.audience = course.assessment_criteria = course.references = "x"
    course.revision_date = course.review_due = "2027-01-01"
    course.save()
    client.force_login(creator)
    client.post(reverse("backoffice:course_workflow", args=[course.pk]), {"action": "submit"})
    client.force_login(reviewer)
    client.post(reverse("backoffice:course_workflow", args=[course.pk]), {"action": "approve", "note": "Looks good"})
    client.force_login(manager)
    client.post(reverse("backoffice:course_workflow", args=[course.pk]), {"action": "publish"})
    course.refresh_from_db()
    assert course.status == Course.PUBLISHED and course.version == 2
    assert list(course.review_comments.values_list("action", flat=True)) == ["published", "approved", "submitted"]


def test_staff_2fa_enforced_when_enabled(client, settings):
    settings.REQUIRE_STAFF_2FA = True
    admin = make_user("boss@example.com", roles=["nis_admin"])
    client.force_login(admin)
    resp = client.get(reverse("backoffice:home"))
    assert resp.status_code == 302 and "/account/2fa/setup/" in resp["Location"]


# --- Accounts -------------------------------------------------------------------------------

def test_signup_records_consent_and_logs_in(client, coach_profession):
    resp = client.post(reverse("accounts:signup"), {
        "first_name": "Ada", "last_name": "Obi", "email": "ada@example.com", "phone": "", "state": "Lagos",
        "professions": [coach_profession.pk], "password1": PW, "password2": PW, "accept_terms": "on",
    })
    assert resp.status_code == 302
    user = User.objects.get(email="ada@example.com")
    assert set(Consent.objects.filter(user=user).values_list("kind", flat=True)) == {"terms", "privacy"}
    assert client.get(reverse("learning:dashboard")).status_code == 200


def test_login_lockout_after_repeated_failures(client, learner):
    for _ in range(8):
        client.post(reverse("accounts:login"), {"username": learner.email, "password": "wrong"})
    resp = client.post(reverse("accounts:login"), {"username": learner.email, "password": PW}, follow=True)
    assert b"Too many failed attempts" in resp.content


def test_data_export_contains_own_data(client, learner, course):
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[course.slug]))
    resp = client.get(reverse("accounts:export_data"))
    assert resp.status_code == 200 and resp["Content-Type"] == "application/zip"


# --- Payments ------------------------------------------------------------------------------

@pytest.fixture
def paid_course(course):
    course.price_kobo = 1500000
    course.save()
    return course


def test_paid_course_test_mode_checkout(client, learner, paid_course):
    client.force_login(learner)
    resp = client.post(reverse("commerce:checkout", args=[paid_course.slug]), {"action": "pay"})
    order = Order.objects.get(user=learner)
    assert resp["Location"] == reverse("commerce:test_gateway", args=[order.reference])
    client.post(resp["Location"], {"outcome": "success"})
    order.refresh_from_db()
    assert order.status == "paid" and order.amount_kobo == 1500000
    assert Enrolment.objects.get(user=learner, course=paid_course).source == "paid"
    assert client.get(reverse("commerce:receipt", args=[order.reference])).status_code == 200


def test_free_enrol_endpoint_refuses_paid_course(client, learner, paid_course):
    client.force_login(learner)
    client.post(reverse("learning:enrol", args=[paid_course.slug]))
    assert not Enrolment.objects.filter(user=learner).exists()


def test_full_scholarship_voucher_enrols_without_payment(client, learner, paid_course):
    Voucher.objects.create(code="SPONSOR100", discount_percent=100, max_uses=1)
    client.force_login(learner)
    client.post(reverse("commerce:checkout", args=[paid_course.slug]), {"action": "pay", "voucher": "sponsor100"})
    assert Enrolment.objects.get(user=learner).source == "sponsored"
    assert Voucher.objects.get(code="SPONSOR100").times_used == 1


def test_refund_by_finance_officer(client, learner, paid_course):
    client.force_login(learner)
    client.post(reverse("commerce:checkout", args=[paid_course.slug]), {"action": "pay"})
    order = Order.objects.get(user=learner)
    client.post(reverse("commerce:test_gateway", args=[order.reference]), {"outcome": "success"})
    finance = make_user("fin@example.com", roles=["finance_officer"])
    client.force_login(finance)
    client.post(reverse("backoffice:order_detail", args=[order.pk]), {"action": "refund", "amount": "15000", "reason": "Duplicate"})
    order.refresh_from_db()
    assert order.status == "refunded" and AuditLog.objects.filter(action="payment.refunded").exists()


# --- Credentials ---------------------------------------------------------------------------

def test_revoked_credential_shows_revoked_publicly(client, learner, course):
    registrar = make_user("reg@example.com", roles=["registrar"])
    cred = cred_services.issue(learner, course.credential_type, course.title, course=course)
    client.force_login(registrar)
    client.post(reverse("backoffice:credential_manage", args=[cred.pk]), {"action": "revoked", "reason": "Exam misconduct"})
    client.logout()
    page = client.get(reverse("credentials:verify_code", args=[cred.code]))
    assert b"has been revoked" in page.content


def test_unknown_code_is_not_found(client, db):
    page = client.get(reverse("credentials:verify_code", args=["SIQ-NOPE-NOPE"]))
    assert b"No credential found" in page.content


def test_api_verify_endpoint(client, learner, course):
    cred = cred_services.issue(learner, course.credential_type, course.title, course=course)
    data = client.get(f"/api/v1/credentials/verify/{cred.code}/").json()
    assert data["found"] and data["status"] == "valid" and data["kind"] == "completion"


# --- Public pages ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", ["/", "/courses/", "/courses/paths/", "/about/", "/institutions/", "/demo/", "/blog/",
                                 "/events/", "/verify/", "/help/", "/help/faqs/", "/p/privacy/", "/robots.txt",
                                 "/sitemap.xml", "/manifest.webmanifest", "/sw.js", "/api/v1/courses/"])
def test_public_pages_load(client, course, url):
    assert client.get(url).status_code == 200
