"""Live academy: classes, webinars, office hours, in-person practical sessions (blueprint Module 8)."""
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel


class LiveSession(TimeStampedModel):
    KINDS = [("class", "Live class"), ("webinar", "Webinar"), ("masterclass", "Masterclass / guest lecture"),
             ("seminar", "CPD seminar"), ("in_person", "In-person practical session")]
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=KINDS, default="class")
    description = models.TextField(blank=True)
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.SET_NULL, related_name="live_sessions")
    cohort = models.ForeignKey("learning.Cohort", null=True, blank=True, on_delete=models.SET_NULL)
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="hosted_sessions")
    co_hosts = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="cohosted_sessions")
    partner_institutions = models.ManyToManyField("institutions.Institution", blank=True,
                                                  help_text="Co-teaching institutions / federations")
    guest_speaker = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    room = models.CharField(max_length=80, blank=True, help_text="Video room name (auto)")
    location = models.CharField(max_length=200, blank=True, help_text="For in-person sessions: venue / training centre")
    capacity = models.PositiveIntegerField(null=True, blank=True)
    is_public = models.BooleanField(default=False, help_text="Open to all learners, not just the course")
    cpd_points = models.DecimalField(max_digits=4, decimal_places=1, default=1)
    record = models.BooleanField(default=False, help_text="Session will be recorded (participants are told on joining)")
    recording_url = models.URLField(blank=True)
    recording_available_until = models.DateField(null=True, blank=True, help_text="Retention limit")
    status = models.CharField(max_length=10, default="scheduled",
                              choices=[("scheduled", "Scheduled"), ("cancelled", "Cancelled"), ("done", "Finished")])

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        if not self.room and self.kind != "in_person":
            self.room = f"SportIQ-{uuid.uuid4().hex[:12]}"
        super().save(*a, **kw)

    @property
    def ends_at(self):
        return self.starts_at + timezone.timedelta(minutes=self.duration_minutes)

    @property
    def is_live(self):
        now = timezone.now()
        return self.starts_at - timezone.timedelta(minutes=15) <= now <= self.ends_at

    @property
    def is_over(self):
        return timezone.now() > self.ends_at

    def join_url(self):
        return f"https://{settings.JITSI_DOMAIN}/{self.room}" if self.room else ""

    def get_absolute_url(self):
        return reverse("live:detail", args=[self.pk])


class Registration(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_registrations")
    attended = models.BooleanField(default=False)
    joined_at = models.DateTimeField(null=True, blank=True)
    recording_consent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("session", "user")]


class Poll(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="polls")
    question = models.CharField(max_length=255)
    options = models.JSONField(default=list)
    is_open = models.BooleanField(default=True)

    def results(self):
        counts = {i: 0 for i in range(len(self.options))}
        for v in self.votes.values_list("option", flat=True):
            counts[v] = counts.get(v, 0) + 1
        total = sum(counts.values()) or 1
        return [{"option": o, "n": counts[i], "pct": round(100 * counts[i] / total)} for i, o in enumerate(self.options)]


class PollVote(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    option = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = [("poll", "user")]


class SessionQuestion(models.Model):
    """Moderated Q&A during a live session."""

    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name="questions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.CharField(max_length=500)
    upvotes = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+")
    is_answered = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False, help_text="Shown to attendees only after the host approves it")
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_answered", "-created_at"]


class OfficeHourSlot(models.Model):
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="office_hours")
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.SET_NULL)
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=20)
    booked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="booked_office_hours")
    topic = models.CharField(max_length=255, blank=True)
    room = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["starts_at"]

    def save(self, *a, **kw):
        self.room = self.room or f"SportIQ-oh-{uuid.uuid4().hex[:10]}"
        super().save(*a, **kw)

    def join_url(self):
        return f"https://{settings.JITSI_DOMAIN}/{self.room}"
