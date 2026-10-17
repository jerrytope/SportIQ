"""Careers & engagement: experience record (CV builder), challenges and team competitions (Modules 14-15)."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

LEVELS = [("grassroots", "Grassroots / community"), ("school", "School sport"), ("club", "Club"),
          ("elite", "Elite / national"), ("disability", "Disability / para-sport"), ("administration", "Administration")]


class Experience(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="experience")
    role = models.CharField(max_length=120)
    organisation = models.CharField(max_length=200)
    sport = models.ForeignKey("catalog.Sport", null=True, blank=True, on_delete=models.SET_NULL)
    level = models.CharField(max_length=15, choices=LEVELS, default="club")
    state = models.CharField(max_length=40, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Leave empty if current")
    description = models.TextField(blank=True)
    verified_by_institution = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]

    @property
    def is_current(self):
        return self.end_date is None


class Challenge(TimeStampedModel):
    METRICS = [("lessons", "Lessons completed"), ("courses", "Courses completed"), ("days", "Active learning days"),
               ("practicals", "Practical tasks passed")]
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    metric = models.CharField(max_length=12, choices=METRICS, default="lessons")
    target = models.PositiveIntegerField(default=10, help_text="Personal target (everyone who reaches it earns the badge)")
    starts_on = models.DateField(default=timezone.localdate)
    ends_on = models.DateField()
    cohort = models.ForeignKey("learning.Cohort", null=True, blank=True, on_delete=models.CASCADE)
    team_mode = models.BooleanField(default=False, help_text="Teams = institutions; ranks institutions by member average")
    show_leaderboard = models.BooleanField(default=False, help_text="Optional; off protects learners with less time/connectivity")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-starts_on"]

    def __str__(self):
        return self.title


class ChallengeEntry(models.Model):
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="challenge_entries")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("challenge", "user")]
