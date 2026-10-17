"""Scheduled jobs. Run via Celery beat in production, or `python manage.py run_daily_jobs` from cron."""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.notifications.services import notify


@shared_task
def inactivity_reminders(days=7):
    from .models import Enrolment

    cutoff = timezone.now() - timedelta(days=days)
    n = 0
    for e in Enrolment.objects.filter(status="active", last_activity_at__lt=cutoff,
                                      last_activity_at__gte=cutoff - timedelta(days=1)).select_related("user", "course"):
        notify(e.user, f"Pick up where you left off: {e.course.title}",
               f"You're {e.progress}% through. A few minutes today keeps your streak alive.", f"/learn/{e.course.slug}/")
        n += 1
    return n


@shared_task
def deadline_reminders():
    from .models import Enrolment

    soon = timezone.localdate() + timedelta(days=3)
    n = 0
    for e in Enrolment.objects.filter(status="active", due_date=soon).select_related("user", "course"):
        notify(e.user, f"Due in 3 days: {e.course.title}", f"You're {e.progress}% complete.", f"/learn/{e.course.slug}/", sms=True)
        n += 1
    return n


@shared_task
def renewal_reminders():
    from apps.credentials.models import Credential

    today = timezone.localdate()
    n = 0
    for days in (60, 30, 7):
        target = today + timedelta(days=days)
        for c in Credential.objects.filter(status="active", expires_at__date=target).select_related("user"):
            notify(c.user, f"Renewal due in {days} days: {c.title}",
                   "Complete the renewal requirements to keep your credential valid.", c.get_absolute_url(), sms=days <= 7)
            n += 1
    return n


@shared_task
def nightly_snapshot():
    from apps.analytics.services import snapshot

    return snapshot()


@shared_task
def outcome_surveys():
    """Longitudinal follow-up 6 and 12 months after completion (Phase 4)."""
    from apps.research.models import OutcomeSurvey

    from .models import Enrolment

    today = timezone.localdate()
    n = 0
    for months in (6, 12):
        lo, hi = today - timedelta(days=30 * months + 3), today - timedelta(days=30 * months)
        for e in Enrolment.objects.filter(status="completed", completed_at__date__range=(lo, hi)).select_related("user", "course"):
            s, created = OutcomeSurvey.objects.get_or_create(enrolment=e, wave=months)
            if created:
                notify(e.user, f"{months} months on: how is {e.course.title} helping?", "Two quick questions help NIS improve training.",
                       f"/research/outcomes/{s.pk}/")
                n += 1
    return n


@shared_task
def scheduled_publishing():
    from apps.catalog.models import Course, ReviewComment

    n = 0
    for c in Course.objects.filter(status=Course.APPROVED, publish_at__lte=timezone.now()):
        c.status, c.version, c.published_at = Course.PUBLISHED, c.version + 1, timezone.now()
        c.save()
        ReviewComment.objects.create(course=c, action="published", body="Published automatically at the scheduled time.")
        n += 1
    return n


@shared_task
def ai_maintenance():
    from apps.ai.services import rebuild_index, scan_risks

    return {"chunks": rebuild_index(), "alerts": scan_risks()}


@shared_task
def scheduled_reports():
    from apps.analytics.services import send_scheduled_reports

    return send_scheduled_reports()


def run_all():
    return {
        "inactivity": inactivity_reminders(),
        "deadlines": deadline_reminders(),
        "renewals": renewal_reminders(),
        "outcome_surveys": outcome_surveys(),
        "scheduled_publishing": scheduled_publishing(),
        "ai": ai_maintenance(),
        "reports": scheduled_reports(),
        "snapshot": bool(nightly_snapshot()),
    }
