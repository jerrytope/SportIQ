from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.accounts.models import STATE_CHOICES
from apps.core.models import TimeStampedModel


class Institution(TimeStampedModel):
    KINDS = [
        ("nis", "NIS department"),
        ("federation", "Sports federation"),
        ("state_council", "State sports council"),
        ("university", "University / college"),
        ("centre", "Training centre"),
        ("employer", "Employer / club"),
        ("partner", "Academic or technical partner"),
    ]
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    kind = models.CharField(max_length=20, choices=KINDS)
    state = models.CharField(max_length=40, choices=STATE_CHOICES, blank=True)
    sport = models.ForeignKey("catalog.Sport", null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="institutions/", blank=True)
    website = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:220]
        super().save(*args, **kwargs)


class Membership(TimeStampedModel):
    """Links a user to an institution. Institution admins see only their own members' records."""

    ROLES = [("admin", "Institution administrator"), ("staff", "Staff member"), ("member", "Member / learner")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=ROLES, default="member")
    job_title = models.CharField(max_length=120, blank=True)
    is_verified = models.BooleanField(default=False, help_text="Institution confirmed this person works with them")

    class Meta:
        unique_together = [("user", "institution")]
        ordering = ["institution__name"]

    def __str__(self):
        return f"{self.user} @ {self.institution} ({self.get_role_display()})"


class Invitation(TimeStampedModel):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=Membership.ROLES, default="member")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    accepted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]


def institutions_admined_by(user):
    if not user.is_authenticated:
        return Institution.objects.none()
    return Institution.objects.filter(memberships__user=user, memberships__role="admin", is_active=True)


def members_visible_to(user):
    """Users whose records an institution admin may see: members of institutions they administer."""
    from apps.accounts.models import User

    return User.objects.filter(memberships__institution__in=institutions_admined_by(user)).distinct()
