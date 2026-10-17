"""Portfolio submissions, rubric grading and supervisor sign-off (blueprint Module 3, Phase 2)."""
import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.core.models import TimeStampedModel


class PracticalTask(TimeStampedModel):
    KINDS = [("session_plan", "Session plan"), ("tactical_report", "Tactical / match report"),
             ("event_plan", "Event plan"), ("business_plan", "Business plan"),
             ("sponsorship", "Sponsorship proposal"), ("budget", "Event budget"),
             ("video", "Video of practice"), ("workplace", "Workplace competence (supervisor sign-off)"),
             ("oral", "Oral / observed assessment")]
    course = models.ForeignKey("catalog.Course", on_delete=models.CASCADE, related_name="practical_tasks")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=KINDS, default="session_plan")
    instructions = models.TextField()
    template_file = models.FileField(upload_to="practicals/templates/", blank=True)
    rubric = models.JSONField(default=list, blank=True,
                              help_text='List of criteria, e.g. [{"title": "Clear objective", "max": 5}]')
    pass_mark = models.PositiveSmallIntegerField(default=60, help_text="Percent of rubric total")
    requires_supervisor = models.BooleanField(default=False,
                                              help_text="A qualified supervisor must confirm the competence was observed")
    accepts_video = models.BooleanField(default=False)

    class Meta:
        ordering = ["course", "title"]

    def __str__(self):
        return self.title

    @property
    def rubric_total(self):
        return sum(int(c.get("max", 0)) for c in self.rubric) or 0


def make_token():
    return secrets.token_urlsafe(24)


class Submission(TimeStampedModel):
    STATUSES = [("submitted", "Awaiting assessment"), ("revise", "Revision requested"), ("passed", "Competent"),
                ("failed", "Not yet competent")]
    task = models.ForeignKey(PracticalTask, on_delete=models.CASCADE, related_name="submissions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="practical_submissions")
    text = models.TextField(blank=True)
    file = models.FileField(upload_to="practicals/submissions/", blank=True)
    video = models.FileField(upload_to="practicals/video/", blank=True)
    video_url = models.URLField(blank=True, help_text="Or a link to an unlisted video")
    status = models.CharField(max_length=10, choices=STATUSES, default="submitted", db_index=True)
    rubric_scores = models.JSONField(default=dict, blank=True)
    score_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    ai_feedback = models.TextField(blank=True, help_text="Preliminary AI feedback (draft for the assessor)")
    assessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    assessed_at = models.DateTimeField(null=True, blank=True)
    supervisor_name = models.CharField(max_length=120, blank=True)
    supervisor_email = models.EmailField(blank=True)
    supervisor_role = models.CharField(max_length=120, blank=True)
    supervisor_token = models.CharField(max_length=64, default=make_token, unique=True)
    supervisor_signed_at = models.DateTimeField(null=True, blank=True)
    supervisor_comment = models.TextField(blank=True)
    attempt = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.task}"

    @property
    def awaiting_supervisor(self):
        return self.task.requires_supervisor and not self.supervisor_signed_at

    def signoff_url(self):
        return reverse("practicals:signoff", args=[self.supervisor_token])
