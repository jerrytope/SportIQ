"""Practical labs & simulators (blueprint Module 3). Every result is a TRAINING EXERCISE, never a qualification."""
from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.catalog.models import unique_slug
from apps.core.models import TimeStampedModel


class Scenario(TimeStampedModel):
    KINDS = [("coaching", "Coaching simulator"), ("refereeing", "Refereeing simulator"),
             ("admin", "Sports administration simulator"), ("event", "Event management sandbox"),
             ("medicine", "Sports medicine case study"), ("research", "Research laboratory"),
             ("match_analysis", "Match analysis laboratory"), ("performance", "Performance analysis laboratory"),
             ("session_designer", "Coaching session designer"), ("budget", "Budget sandbox")]
    ENGINES = [("branching", "Branching decisions"), ("annotate", "Video annotation + report"),
               ("load", "Training-load calculator"), ("designer", "Session designer"), ("budget", "Budget allocation")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    kind = models.CharField(max_length=16, choices=KINDS)
    engine = models.CharField(max_length=10, choices=ENGINES, default="branching")
    summary = models.CharField(max_length=300)
    intro = models.TextField(blank=True)
    video = models.FileField(upload_to="labs/video/", blank=True)
    hls_playlist = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict, help_text="Engine-specific content: nodes, dataset, drills, budget lines…")
    sport = models.ForeignKey("catalog.Sport", null=True, blank=True, on_delete=models.SET_NULL)
    professions = models.ManyToManyField("catalog.Profession", blank=True)
    requires_qualified = models.BooleanField(default=False,
                                             help_text="Restricted to learners with a verified professional profile (e.g. medical cases)")
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "title"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("labs:play", args=[self.slug])


class Run(TimeStampedModel):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="runs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lab_runs")
    path = models.JSONField(default=list, help_text="Choices made / annotations / allocations")
    score = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Training score 0-100")
    feedback = models.JSONField(default=list, blank=True)
    report = models.TextField(blank=True)
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
