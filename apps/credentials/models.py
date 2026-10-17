import secrets
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel


class CredentialType(models.Model):
    """Blueprint Module 5: a completion certificate is not a competence, a qualification or a licence."""

    COMPLETION, COMPETENCE, QUALIFICATION, LICENCE = "completion", "competence", "qualification", "licence"
    KINDS = [
        (COMPLETION, "Course completion certificate"),
        (COMPETENCE, "Assessed competence"),
        (QUALIFICATION, "Professional qualification"),
        (LICENCE, "Licence (issued by governing body)"),
    ]
    KIND_EXPLAINERS = {
        COMPLETION: "Confirms the holder completed the online course and passed its assessment. "
                    "It is not a professional licence.",
        COMPETENCE: "Confirms competence demonstrated in a supervised practical assessment.",
        QUALIFICATION: "An NIS-approved professional qualification awarded after all required "
                       "courses, examinations and practical assessments.",
        LICENCE: "A licence issued by the relevant governing body. SportIQ records it; it does not issue it.",
    }
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=15, choices=KINDS)
    description = models.TextField(blank=True)
    validity_months = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Empty = does not expire")
    cpd_points_for_renewal = models.PositiveSmallIntegerField(default=0, help_text="Approved CPD points needed per cycle to renew")
    issuer_name = models.CharField(max_length=120, default="National Institute for Sports")

    def __str__(self):
        return self.name

    @property
    def explainer(self):
        return self.KIND_EXPLAINERS.get(self.kind, "")


def make_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "SIQ-" + "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2))


class Credential(TimeStampedModel):
    ACTIVE, SUSPENDED, REVOKED = "active", "suspended", "revoked"
    STATUSES = [(ACTIVE, "Active"), (SUSPENDED, "Suspended"), (REVOKED, "Revoked")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, default=make_code, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="credentials")
    credential_type = models.ForeignKey(CredentialType, on_delete=models.PROTECT)
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.SET_NULL)
    course_version = models.PositiveIntegerField(null=True, blank=True)
    title = models.CharField(max_length=200)
    holder_name = models.CharField(max_length=200, help_text="Name as printed at issue")
    grade = models.CharField(max_length=40, blank=True)
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=ACTIVE, db_index=True)
    status_reason = models.TextField(blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.code} · {self.title}"

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at < timezone.now())

    @property
    def effective_status(self):
        if self.status != self.ACTIVE:
            return self.status
        return "expired" if self.is_expired else "valid"

    @property
    def is_valid(self):
        return self.effective_status == "valid"

    def get_verify_url(self):
        return reverse("credentials:verify_code", args=[self.code])

    def get_absolute_url(self):
        return reverse("credentials:detail", args=[self.pk])


class CredentialEvent(models.Model):
    ACTIONS = [("issued", "Issued"), ("suspended", "Suspended"), ("revoked", "Revoked"),
               ("reinstated", "Reinstated"), ("corrected", "Corrected"), ("renewed", "Renewed")]
    credential = models.ForeignKey(Credential, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=12, choices=ACTIONS)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class VerificationLog(models.Model):
    credential = models.ForeignKey(Credential, null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="verifications")
    query = models.CharField(max_length=60)
    found = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MandatoryRequirement(models.Model):
    """e.g. every Coach must hold a current Safeguarding certificate (blueprint Module 13)."""

    profession = models.ForeignKey("catalog.Profession", on_delete=models.CASCADE, related_name="requirements")
    course = models.ForeignKey("catalog.Course", on_delete=models.CASCADE, related_name="mandatory_for")
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = [("profession", "course")]

    def __str__(self):
        return f"{self.profession}: {self.course}"


# --- Phase 2: qualifications, CPD, renewals, prior learning ---------------------------------

class Programme(TimeStampedModel):
    """An NIS qualification made of required courses (+ optional supervised practicals)."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    credential_type = models.ForeignKey(CredentialType, on_delete=models.PROTECT,
                                        limit_choices_to={"kind__in": ["qualification", "competence"]})
    courses = models.ManyToManyField("catalog.Course", related_name="programmes")
    practical_tasks = models.ManyToManyField("practicals.PracticalTask", blank=True, related_name="programmes",
                                             help_text="Supervised practicals that must be passed")
    requires_application = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("credentials:programme", args=[self.slug])

    def programme_applications_ok(self, user):
        return not self.requires_application or self.applications.filter(user=user, status="admitted").exists()


class ProgrammeApplication(TimeStampedModel):
    STATUSES = [("submitted", "Submitted"), ("admitted", "Admitted"), ("rejected", "Not admitted")]
    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name="applications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="programme_applications")
    statement = models.TextField()
    document = models.FileField(upload_to="applications/", blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="submitted")
    decision_note = models.TextField(blank=True)

    class Meta:
        unique_together = [("programme", "user")]


class CPDActivity(TimeStampedModel):
    KINDS = [("course", "SportIQ course"), ("live", "Live session / webinar"), ("event", "Workshop or conference"),
             ("external", "External course"), ("practice", "Supervised practice"), ("other", "Other")]
    STATUSES = [("pending", "Awaiting approval"), ("approved", "Approved"), ("rejected", "Not approved")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cpd_activities")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=KINDS, default="external")
    provider = models.CharField(max_length=200, blank=True)
    date = models.DateField(default=timezone.localdate)
    hours = models.DecimalField(max_digits=5, decimal_places=1, default=1)
    points = models.DecimalField(max_digits=5, decimal_places=1, default=0, help_text="Set on approval")
    evidence = models.FileField(upload_to="cpd/", blank=True)
    reflection = models.TextField(blank=True, help_text="What did you learn and how will you apply it?")
    status = models.CharField(max_length=10, choices=STATUSES, default="pending", db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    review_note = models.CharField(max_length=255, blank=True)
    source_key = models.CharField(max_length=60, blank=True, help_text="Prevents duplicate automatic records")

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "CPD activities"


class RenewalRequest(TimeStampedModel):
    STATUSES = [("pending", "Pending"), ("approved", "Renewed"), ("rejected", "Not approved")]
    credential = models.ForeignKey(Credential, on_delete=models.CASCADE, related_name="renewal_requests")
    cpd_points = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]


class PriorLearningClaim(TimeStampedModel):
    """Recognition of prior learning (RPL): evidence-based exemption from a course."""

    STATUSES = [("submitted", "Submitted"), ("approved", "Recognised"), ("rejected", "Not recognised")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rpl_claims")
    course = models.ForeignKey("catalog.Course", on_delete=models.CASCADE, related_name="rpl_claims")
    statement = models.TextField(help_text="Describe the equivalent learning or experience")
    evidence = models.FileField(upload_to="rpl/")
    status = models.CharField(max_length=10, choices=STATUSES, default="submitted")
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["-created_at"]


class ExternalQualification(TimeStampedModel):
    """A qualification or licence from another awarding body, recorded after verification (never re-issued)."""

    STATUSES = [("submitted", "Awaiting verification"), ("verified", "Verified"), ("rejected", "Could not verify")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_qualifications")
    title = models.CharField(max_length=200)
    awarding_body = models.CharField(max_length=200)
    reference = models.CharField(max_length=100, blank=True)
    awarded_on = models.DateField()
    expires_on = models.DateField(null=True, blank=True)
    evidence = models.FileField(upload_to="external-quals/")
    status = models.CharField(max_length=10, choices=STATUSES, default="submitted")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-awarded_on"]
