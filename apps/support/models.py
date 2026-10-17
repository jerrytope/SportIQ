from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


class HelpCategory(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "help categories"

    def __str__(self):
        return self.name

    def save(self, *a, **kw):
        self.slug = self.slug or slugify(self.name)
        super().save(*a, **kw)


class HelpArticle(TimeStampedModel):
    category = models.ForeignKey(HelpCategory, on_delete=models.CASCADE, related_name="articles")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    body = models.TextField(help_text="Markdown")
    is_faq = models.BooleanField(default=False, help_text="Also show in the FAQ list")
    is_published = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        self.slug = self.slug or slugify(self.title)[:200]
        super().save(*a, **kw)


SLA_HOURS = {"urgent": 4, "high": 24, "normal": 48, "low": 96}


class Ticket(TimeStampedModel):
    CATEGORIES = [("technical", "Technical (login, downloads, video)"), ("academic", "Academic (course, assessment)"),
                  ("payment", "Payment"), ("certificate", "Certificate / verification"),
                  ("accessibility", "Accessibility assistance"), ("complaint", "Formal complaint")]
    PRIORITIES = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]
    STATUSES = [("open", "Open"), ("pending", "Waiting on learner"), ("resolved", "Resolved"), ("closed", "Closed")]
    reference = models.CharField(max_length=16, unique=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tickets")
    category = models.CharField(max_length=15, choices=CATEGORIES)
    priority = models.CharField(max_length=10, choices=PRIORITIES, default="normal")
    status = models.CharField(max_length=10, choices=STATUSES, default="open", db_index=True)
    subject = models.CharField(max_length=200)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="assigned_tickets")
    sla_due = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.subject}"

    def save(self, *a, **kw):
        if self.category == "complaint" and self.priority == "normal":
            self.priority = "high"
        if not self.sla_due:
            self.sla_due = timezone.now() + timedelta(hours=SLA_HOURS[self.priority])
        super().save(*a, **kw)
        if not self.reference:
            self.reference = f"T{self.pk:06d}"
            super().save(update_fields=["reference"])

    @property
    def is_overdue(self):
        return self.status in ("open", "pending") and self.sla_due and self.sla_due < timezone.now()


class TicketMessage(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    attachment = models.FileField(upload_to="tickets/", blank=True)
    is_internal = models.BooleanField(default=False, help_text="Staff-only note")

    class Meta:
        ordering = ["created_at"]


class StatusNotice(models.Model):
    """Service interruption / maintenance announcement shown as a site-wide banner."""

    LEVELS = [("info", "Information"), ("warning", "Maintenance"), ("danger", "Service interruption")]
    message = models.CharField(max_length=255)
    level = models.CharField(max_length=10, choices=LEVELS, default="info")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return self.message

    @classmethod
    def current(cls):
        now = timezone.now()
        return cls.objects.filter(is_active=True, starts_at__lte=now).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
