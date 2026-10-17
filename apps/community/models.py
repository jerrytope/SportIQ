"""Professional community, mentorship and opportunities (blueprint Module 10)."""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse

from apps.catalog.models import unique_slug
from apps.core.models import TimeStampedModel


class Group(TimeStampedModel):
    KINDS = [("sport", "Sport"), ("discipline", "Discipline"), ("alumni", "Alumni"), ("roundtable", "Expert roundtable"),
             ("network", "Professional network")]
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    kind = models.CharField(max_length=12, choices=KINDS, default="discipline")
    description = models.TextField(blank=True)
    sport = models.ForeignKey("catalog.Sport", null=True, blank=True, on_delete=models.SET_NULL)
    profession = models.ForeignKey("catalog.Profession", null=True, blank=True, on_delete=models.SET_NULL)
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.SET_NULL,
                               help_text="Alumni groups: open to people who completed this course")
    is_private = models.BooleanField(default=False, help_text="Join requests need moderator approval")
    verified_only = models.BooleanField(default=False, help_text="Only verified professionals may post")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through="GroupMember", related_name="community_groups")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(self, self.name, max_length=160)
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("community:group", args=[self.slug])


class GroupMember(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, default="member", choices=[("member", "Member"), ("moderator", "Moderator")])
    approved = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("group", "user")]


class Discussion(TimeStampedModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="discussions")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title


class Reply(TimeStampedModel):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]


class ContentReport(TimeStampedModel):
    """Report button on posts, discussions, profiles and opportunities."""

    REASONS = [("abuse", "Harassment or abuse"), ("spam", "Spam or scam"), ("misinfo", "False information"),
               ("safeguarding", "Safeguarding concern"), ("other", "Other")]
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="content_reports")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    reason = models.CharField(max_length=12, choices=REASONS)
    detail = models.TextField(blank=True)
    status = models.CharField(max_length=10, default="open", choices=[("open", "Open"), ("actioned", "Actioned"),
                                                                    ("dismissed", "Dismissed")])
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]


class MentorProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentor_profile")
    headline = models.CharField(max_length=200)
    areas = models.CharField(max_length=255, help_text="Comma-separated areas of expertise")
    sports = models.ManyToManyField("catalog.Sport", blank=True)
    professions = models.ManyToManyField("catalog.Profession", blank=True)
    capacity = models.PositiveSmallIntegerField(default=3, help_text="Active mentees at a time")
    is_available = models.BooleanField(default=True)
    approved = models.BooleanField(default=False, help_text="Approved by NIS before listing")

    def __str__(self):
        return f"Mentor: {self.user}"

    @property
    def active_mentees(self):
        return self.requests.filter(status="active").count()


class MentorshipRequest(TimeStampedModel):
    STATUSES = [("pending", "Pending"), ("active", "Active"), ("declined", "Declined"), ("completed", "Completed")]
    mentor = models.ForeignKey(MentorProfile, on_delete=models.CASCADE, related_name="requests")
    mentee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentorship_requests")
    goals = models.TextField()
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")
    next_meeting_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class Opportunity(TimeStampedModel):
    KINDS = [("job", "Job"), ("internship", "Internship"), ("volunteer", "Volunteering"),
             ("apprenticeship", "Apprenticeship"), ("research", "Research project"), ("event", "Professional event")]
    STATUSES = [("pending", "Awaiting approval"), ("open", "Open"), ("closed", "Closed"), ("rejected", "Rejected")]
    kind = models.CharField(max_length=15, choices=KINDS)
    title = models.CharField(max_length=200)
    organisation = models.CharField(max_length=200)
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField()
    requirements = models.TextField(blank=True)
    required_credential = models.ForeignKey("credentials.CredentialType", null=True, blank=True, on_delete=models.SET_NULL)
    sport = models.ForeignKey("catalog.Sport", null=True, blank=True, on_delete=models.SET_NULL)
    profession = models.ForeignKey("catalog.Profession", null=True, blank=True, on_delete=models.SET_NULL)
    state = models.CharField(max_length=40, blank=True)
    location = models.CharField(max_length=200, blank=True)
    paid = models.BooleanField(default=True)
    closes_on = models.DateField(null=True, blank=True)
    apply_url = models.URLField(blank=True, help_text="Leave empty to receive applications on SportIQ")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="posted_opportunities")
    status = models.CharField(max_length=10, choices=STATUSES, default="pending", db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "opportunities"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("community:opportunity", args=[self.pk])


class OpportunityApplication(TimeStampedModel):
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="applications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="opportunity_applications")
    cover_note = models.TextField()
    share_profile = models.BooleanField(default=True, help_text="Share my verified credentials and CV with the poster")
    status = models.CharField(max_length=12, default="submitted",
                              choices=[("submitted", "Submitted"), ("shortlisted", "Shortlisted"), ("unsuccessful", "Unsuccessful")])

    class Meta:
        unique_together = [("opportunity", "user")]
        ordering = ["-created_at"]
