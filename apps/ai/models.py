"""AI study assistant (blueprint Module 4): retrieval over approved content, conversations, study plans, alerts."""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Chunk(models.Model):
    """A passage of approved NIS content the assistant may cite."""

    SOURCES = [("lesson", "Course lesson"), ("transcript", "Lesson transcript"), ("library", "Library resource"),
               ("help", "Help centre"), ("course", "Course overview")]
    source_type = models.CharField(max_length=10, choices=SOURCES)
    source_id = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    url = models.CharField(max_length=255)
    text = models.TextField()
    version = models.CharField(max_length=20, blank=True)
    tokens = models.JSONField(default=list, help_text="Normalised terms for retrieval")
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["source_type", "source_id"])]


class Conversation(TimeStampedModel):
    MODES = [("tutor", "Study assistant"), ("support", "Help & support"), ("copilot", "Instructor copilot")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_conversations")
    mode = models.CharField(max_length=10, choices=MODES, default="tutor")
    title = models.CharField(max_length=200, blank=True)
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.SET_NULL)
    escalated_ticket = models.ForeignKey("support.Ticket", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-updated_at"]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=[("user", "User"), ("assistant", "Assistant")])
    content = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    engine = models.CharField(max_length=40, blank=True, help_text="claude model id or 'retrieval'")
    refused = models.BooleanField(default=False)
    helpful = models.BooleanField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class StudyPlan(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_plans")
    goal = models.CharField(max_length=255)
    hours_per_week = models.PositiveSmallIntegerField(default=3)
    weeks = models.JSONField(default=list, help_text="[{week, items:[{course, lesson, minutes}]}]")
    narrative = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]


class RiskAlert(TimeStampedModel):
    KINDS = [("inactive", "Inactive for 14+ days"), ("repeat_fail", "Repeated assessment failures"),
             ("stalled", "No progress before deadline")]
    enrolment = models.ForeignKey("learning.Enrolment", on_delete=models.CASCADE, related_name="risk_alerts")
    kind = models.CharField(max_length=12, choices=KINDS)
    detail = models.CharField(max_length=255)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("enrolment", "kind", "resolved")]
