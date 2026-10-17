import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Immutable record of consequential actions (approvals, grades, credentials, permissions, exports)."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries"
    )
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.object_repr}"


class SiteSettings(models.Model):
    """Singleton: landing-page copy, contact details and platform feature flags, editable in the back office."""

    announcement_text = models.CharField(
        max_length=200, blank=True,
        default="Now enrolling: Safeguarding & Anti-Doping Essentials, free for registered coaches.",
    )
    announcement_link = models.CharField(max_length=200, blank=True, default="/courses/")
    hero_eyebrow = models.CharField(max_length=40, default="New")
    hero_title = models.CharField(max_length=160, default="Learn the game. Prove your skill. Grow Nigerian sport.")
    hero_subtitle = models.TextField(
        default=(
            "SportIQ is the national digital academy for coaches, referees, administrators, sports scientists "
            "and athletes: expert-led courses, verifiable qualifications and continuous professional development "
            "with the National Institute for Sports."
        )
    )
    contact_email = models.EmailField(default="hello@sportiq.edu.ng")
    contact_phone = models.CharField(max_length=40, default="+234 800 000 0000")
    address = models.CharField(max_length=200, default="National Institute for Sports, National Stadium, Surulere, Lagos")
    linkedin_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    # Feature flags
    leaderboards_enabled = models.BooleanField(default=False)
    public_registration_open = models.BooleanField(default=True)
    support_hours = models.CharField(max_length=120, default="Mon–Fri, 8:00–17:00 WAT")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def new_uuid():
    return uuid.uuid4()


def add_months(dt, months):
    """Same day-of-month `months` later (clamped to month end), keeping the time."""
    import calendar

    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)
