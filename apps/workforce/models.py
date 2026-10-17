"""National sports workforce database (blueprint Module 11)."""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class WorkforceProfile(TimeStampedModel):
    """Voluntary, consented directory listing. Unverified profiles are never presented as proof of competence."""

    AVAILABILITY = [("not_looking", "Not looking"), ("open", "Open to opportunities"), ("employed_open", "Employed, open to offers"),
                    ("volunteer", "Volunteering only")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workforce_profile")
    listed = models.BooleanField(default=False, help_text="Appear in authorised workforce searches")
    availability = models.CharField(max_length=14, choices=AVAILABILITY, default="not_looking")
    preferred_states = models.JSONField(default=list, blank=True)
    willing_to_relocate = models.BooleanField(default=False)
    experience_levels = models.JSONField(default=list, blank=True, help_text="grassroots, school, club, elite, disability")
    specialisations = models.CharField(max_length=255, blank=True)
    years_experience = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Workforce profile: {self.user}"


class DirectorySearch(models.Model):
    """Every authorised search is logged (who searched, for what)."""

    searched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.SET_NULL)
    filters = models.JSONField()
    results = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ContactRequest(TimeStampedModel):
    """Employers can't see contact details; they send a request the professional may accept."""

    STATUSES = [("pending", "Pending"), ("accepted", "Accepted"), ("declined", "Declined")]
    professional = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contact_requests")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    institution = models.ForeignKey("institutions.Institution", null=True, on_delete=models.SET_NULL)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")

    class Meta:
        ordering = ["-created_at"]
