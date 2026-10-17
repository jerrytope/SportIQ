"""Metric calculations for dashboards. Every metric has a written definition (blueprint Module 18)."""
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.accounts.models import User
from apps.credentials.models import Credential, VerificationLog
from apps.learning.models import ActivityDay, CourseFeedback, Enrolment

from .models import MetricDefinition, MetricSnapshot

DEFINITIONS = [
    ("registrations", "Registered learners", "Accounts created (excluding staff-only accounts) in the period.", "Learners"),
    ("active_learners", "Active learners", "Learners with at least one day of learning activity in the last 30 days. "
                                           "Not the same as registrations.", "Learners"),
    ("enrolments", "Enrolments", "Course enrolments started in the period.", "Learning"),
    ("completions", "Course completions", "Enrolments that met the course completion rules (all lessons and, where "
                                          "required, the final assessment passed). Completion is not competence.", "Learning"),
    ("completion_rate", "Completion rate", "Completions ÷ enrolments that started at least 30 days ago.", "Learning"),
    ("certificates", "Certificates issued", "Credentials issued in the period, of any type.", "Qualifications"),
    ("verifications", "Verification checks", "Public verification look-ups that found a credential.", "Qualifications"),
    ("renewals_due", "Renewals due (60 days)", "Active credentials that expire in the next 60 days.", "Qualifications"),
    ("satisfaction", "Learner satisfaction", "Average overall course rating (1–5) from end-of-course feedback.", "Quality"),
    ("revenue", "Course revenue (₦)", "Paid orders minus refunds, in naira. Excludes sponsored seats.", "Resources"),
]


def ensure_definitions():
    for i, (code, name, definition, group) in enumerate(DEFINITIONS):
        MetricDefinition.objects.update_or_create(code=code, defaults={"name": name, "definition": definition,
                                                                       "group": group, "order": i})


def learners_qs(state=None, profession=None, institution=None):
    qs = User.objects.filter(is_active=True, staff_roles=[])
    if state:
        qs = qs.filter(state=state)
    if profession:
        qs = qs.filter(professions__slug=profession)
    if institution is not None:
        qs = qs.filter(memberships__institution=institution)
    return qs.distinct()


def compute(start, end, state=None, profession=None, institution=None):
    from apps.commerce.models import Order, Refund

    learners = learners_qs(state, profession, institution)
    ids = learners.values("pk")
    enr = Enrolment.objects.filter(user__in=ids)
    period_enr = enr.filter(created_at__date__range=(start, end))
    mature = enr.filter(created_at__lte=timezone.now() - timedelta(days=30))
    completions = enr.filter(completed_at__date__range=(start, end)).count()
    creds = Credential.objects.filter(user__in=ids)
    paid = Order.objects.filter(user__in=ids, status__in=["paid", "refunded"], paid_at__date__range=(start, end))
    refunds = Refund.objects.filter(order__user__in=ids, created_at__date__range=(start, end))
    revenue_kobo = (paid.aggregate(s=Sum("amount_kobo"))["s"] or 0) - (refunds.aggregate(s=Sum("amount_kobo"))["s"] or 0)
    sat = CourseFeedback.objects.filter(enrolment__user__in=ids).aggregate(a=Avg("course_rating"))["a"]
    return {
        "registrations": learners.filter(date_joined__date__range=(start, end)).count(),
        "total_learners": learners.count(),
        "active_learners": ActivityDay.objects.filter(user__in=ids, date__gte=timezone.localdate() - timedelta(days=30))
        .values("user").distinct().count(),
        "enrolments": period_enr.count(),
        "completions": completions,
        "completion_rate": round(100 * mature.filter(status="completed").count() / mature.count()) if mature.count() else 0,
        "certificates": creds.filter(issued_at__date__range=(start, end)).count(),
        "verifications": VerificationLog.objects.filter(credential__in=creds, found=True,
                                                        created_at__date__range=(start, end)).count(),
        "renewals_due": creds.filter(status="active", expires_at__gte=timezone.now(),
                                     expires_at__lte=timezone.now() + timedelta(days=60)).count(),
        "satisfaction": round(sat, 1) if sat else None,
        "revenue": revenue_kobo / 100,
    }


def breakdown_by_state(state=None, profession=None, institution=None):
    rows = (learners_qs(state, profession, institution).exclude(state="").values("state")
            .annotate(n=Count("pk", distinct=True), done=Count("enrolments", filter=Q(enrolments__status="completed")))
            .order_by("-n"))
    return list(rows)


def breakdown_by_profession(state=None, institution=None):
    from apps.catalog.models import Profession

    base = learners_qs(state, None, institution)
    return [{"name": p.name, "n": base.filter(professions=p).count()} for p in Profession.objects.all()]


def course_table(institution=None):
    from apps.catalog.models import Course

    qs = Course.objects.filter(status="published").annotate(
        enrolled=Count("enrolments", distinct=True),
        completed=Count("enrolments", filter=Q(enrolments__status="completed"), distinct=True),
        rating=Avg("enrolments__feedback__course_rating"),
    ).order_by("-enrolled")
    rows = []
    for c in qs:
        rows.append({"course": c, "enrolled": c.enrolled, "completed": c.completed,
                     "rate": round(100 * c.completed / c.enrolled) if c.enrolled else 0,
                     "rating": round(c.rating, 1) if c.rating else None})
    return rows


def monthly_registrations(months=12, state=None, profession=None, institution=None):
    since = (timezone.now() - timedelta(days=31 * months)).replace(day=1)
    rows = (learners_qs(state, profession, institution).filter(date_joined__gte=since)
            .annotate(m=TruncMonth("date_joined")).values("m").annotate(n=Count("pk")).order_by("m"))
    data = {r["m"].strftime("%Y-%m"): r["n"] for r in rows}
    out, d = [], since.date()
    for _ in range(months + 1):
        key = d.strftime("%Y-%m")
        out.append({"label": d.strftime("%b"), "n": data.get(key, 0)})
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    peak = max((o["n"] for o in out), default=0) or 1
    for o in out:
        o["h"] = round(100 * o["n"] / peak)
    return out[-12:]


def snapshot(day=None):
    """Nightly: store headline metrics so trends survive data changes."""
    day = day or timezone.localdate()
    values = compute(day.replace(day=1), day)
    for code, value in values.items():
        if value is None:
            continue
        MetricSnapshot.objects.update_or_create(date=day, code=code, defaults={"value": value})
    return values



# --- Phase 3/4: impact, delivery comparison, observatory, scheduled reports ---------------------------

SUPPRESS = 5  # public observatory hides groups smaller than this


def pre_post():
    """Mean pre-test vs final-assessment score per course (same learners only)."""
    from apps.assessments.models import Attempt, Exam

    rows = []
    for pre in Exam.objects.filter(is_pretest=True).select_related("course"):
        final = pre.course.final_exam()
        if not final:
            continue
        pre_scores = {a.user_id: float(a.percent) for a in Attempt.objects.filter(exam=pre, percent__isnull=False).order_by("started_at")}
        post_scores = {}
        for a in Attempt.objects.filter(exam=final, status="released", percent__isnull=False).order_by("-percent"):
            post_scores.setdefault(a.user_id, float(a.percent))
        both = [u for u in pre_scores if u in post_scores]
        if both:
            before = sum(pre_scores[u] for u in both) / len(both)
            after = sum(post_scores[u] for u in both) / len(both)
            rows.append({"course": pre.course, "n": len(both), "before": round(before), "after": round(after), "gain": round(after - before)})
    return rows


def by_delivery():
    from apps.catalog.models import FORMATS

    out = []
    for value, label in FORMATS:
        enr = Enrolment.objects.filter(course__delivery_format=value, created_at__lte=timezone.now() - timedelta(days=30))
        n = enr.count()
        done = enr.filter(status="completed").count()
        out.append({"format": label, "n": n, "rate": round(100 * done / n) if n else None})
    return out


def outcome_summary():
    from apps.research.models import OutcomeSurvey

    qs = OutcomeSurvey.objects.filter(responded_at__isnull=False)
    n = qs.count()
    if not n:
        return {"n": 0}
    return {"n": n, "sent": OutcomeSurvey.objects.count(),
            "applied": round(qs.aggregate(a=Avg("applied_learning"))["a"] or 0, 1),
            "progressed": round(100 * qs.filter(role_change__in=["new_role", "promotion", "new_qualification"]).count() / n),
            "employed": round(100 * qs.filter(employed_in_sport=True).count() / n)}


def impact_summary():
    return {"pre_post": pre_post(), "delivery": by_delivery(), "outcomes": outcome_summary(),
            "cohorts": cohort_comparison()}


def cohort_comparison():
    from apps.learning.models import Cohort

    rows = []
    for c in Cohort.objects.select_related("course").annotate(n=Count("enrolments"),
                                                               done=Count("enrolments", filter=Q(enrolments__status="completed"))):
        if c.n:
            rows.append({"cohort": c, "n": c.n, "rate": round(100 * c.done / c.n)})
    return rows


def observatory():
    """Public, aggregated, privacy-safe figures."""
    from apps.catalog.models import Course, Profession
    from apps.credentials.models import Credential

    learners = learners_qs()
    by_state = [r for r in breakdown_by_state() if r["n"] >= SUPPRESS]
    by_prof = [r for r in breakdown_by_profession() if r["n"] >= SUPPRESS]
    return {
        "learners": learners.count(), "states": len(by_state), "courses": Course.objects.published().count(),
        "completions": Enrolment.objects.filter(status="completed").count(),
        "credentials": Credential.objects.filter(status="active").count(),
        "verifications": VerificationLog.objects.filter(found=True).count(),
        "by_state": by_state, "by_prof": by_prof, "monthly": monthly_registrations(),
        "delivery": by_delivery(), "outcomes": outcome_summary(), "pre_post": pre_post(),
        "suppress": SUPPRESS, "professions": Profession.objects.count(),
    }


def send_scheduled_reports(force=False):
    import csv
    import io

    from django.core.mail import EmailMessage

    from .models import ScheduledReport

    today = timezone.localdate()
    sent = 0
    for r in ScheduledReport.objects.filter(is_active=True):
        due = force or (r.frequency == "weekly" and today.weekday() == 0) or (r.frequency == "monthly" and today.day == 1)
        if not due or (r.last_sent and r.last_sent.date() == today and not force):
            continue
        start = today - timedelta(days=7 if r.frequency == "weekly" else 30)
        data = compute(start, today, r.state or None, r.profession or None)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Metric", "Value", "Definition"])
        defs = {c: (n, d) for c, n, d, _ in DEFINITIONS}
        for code, value in data.items():
            name, definition = defs.get(code, (code, ""))
            w.writerow([name, value, definition])
        msg = EmailMessage(f"SportIQ report: {r.name} ({start} to {today})",
                           "Attached: SportIQ figures for the period. Registrations are not active learners and completion is not competence.",
                           to=[e.strip() for e in r.recipients.splitlines() if e.strip()])
        msg.attach(f"sportiq-{today}.csv", buf.getvalue(), "text/csv")
        msg.send(fail_silently=True)
        r.last_sent = timezone.now()
        r.save(update_fields=["last_sent"])
        sent += 1
    return sent
