"""Sports research, data and intelligence centre (blueprint Module 12) + longitudinal outcomes (Phase 4)."""
from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.catalog.models import unique_slug
from apps.core.models import TimeStampedModel


class Project(TimeStampedModel):
    STATUSES = [("proposal", "Proposal"), ("ethics", "Awaiting ethics approval"), ("active", "Active"),
                ("complete", "Complete"), ("rejected", "Not approved")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    lead = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="led_projects")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="research_projects")
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.SET_NULL)
    summary = models.TextField()
    research_question = models.TextField()
    methods = models.TextField(blank=True)
    involves_human_participants = models.BooleanField(default=True)
    involves_children = models.BooleanField(default=False)
    uses_athlete_data = models.BooleanField(default=False)
    ethics_checklist = models.JSONField(default=dict, blank=True)
    ethics_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="proposal")
    recruiting = models.BooleanField(default=False, help_text="Show on the opportunities board as open to collaborators")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("research:project", args=[self.slug])


class Dataset(TimeStampedModel):
    ACCESS = [("open", "Open teaching dataset"), ("approval", "On approved request"), ("restricted", "Restricted (personal data)")]
    title = models.CharField(max_length=200)
    description = models.TextField()
    file = models.FileField(upload_to="research/datasets/")
    access = models.CharField(max_length=10, choices=ACCESS, default="approval")
    contains_personal_data = models.BooleanField(default=False)
    is_anonymised = models.BooleanField(default=True)
    licence = models.CharField(max_length=120, default="CC BY 4.0 (teaching use)")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="datasets")
    variables = models.TextField(blank=True, help_text="Data dictionary")

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class DatasetRequest(TimeStampedModel):
    STATUSES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")]
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dataset_requests")
    purpose = models.TextField()
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL)
    agrees_to_terms = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    expires_on = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = [("dataset", "user")]


class Publication(TimeStampedModel):
    KINDS = [("paper", "Research paper"), ("brief", "Evidence summary for policy-makers"), ("report", "Evaluation report")]
    STATUSES = [("draft", "Draft"), ("review", "In peer review"), ("revise", "Revisions requested"),
                ("published", "Published"), ("rejected", "Rejected")]
    title = models.CharField(max_length=255)
    kind = models.CharField(max_length=8, choices=KINDS, default="paper")
    authors = models.CharField(max_length=255)
    abstract = models.TextField()
    file = models.FileField(upload_to="research/publications/", blank=True)
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="publications")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUSES, default="draft")
    published_on = models.DateField(null=True, blank=True)
    doi = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-published_on", "-created_at"]

    def __str__(self):
        return self.title


class PeerReview(TimeStampedModel):
    RECS = [("accept", "Accept"), ("minor", "Minor revisions"), ("major", "Major revisions"), ("reject", "Reject")]
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recommendation = models.CharField(max_length=6, choices=RECS, blank=True)
    comments = models.TextField(blank=True)
    submitted = models.BooleanField(default=False)


class OutcomeSurvey(TimeStampedModel):
    """Longitudinal follow-up 6 and 12 months after completion (blueprint §8 'demonstrate long-term value')."""

    enrolment = models.ForeignKey("learning.Enrolment", on_delete=models.CASCADE, related_name="outcome_surveys")
    wave = models.PositiveSmallIntegerField(choices=[(6, "6 months"), (12, "12 months")])
    sent_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    applied_learning = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1-5")
    role_change = models.CharField(max_length=20, blank=True, choices=[("none", "No change"), ("new_role", "New role"),
                                                                        ("promotion", "Promotion / more responsibility"),
                                                                        ("new_qualification", "Further qualification")])
    employed_in_sport = models.BooleanField(null=True)
    comment = models.TextField(blank=True)
    consent_research = models.BooleanField(default=False)

    class Meta:
        unique_together = [("enrolment", "wave")]
