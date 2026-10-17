"""Open architecture (blueprint Module 19): API keys, webhooks, xAPI, SCORM, LTI 1.3, SSO identities."""
import hashlib
import secrets

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel

SCOPES = [("courses:read", "Read course catalogue"), ("credentials:verify", "Verify credentials"),
          ("credentials:read", "Read credentials of the key's institution members"),
          ("enrolments:read", "Read enrolments of the key's institution members"), ("xapi:write", "Send xAPI statements"),
          ("xapi:read", "Read xAPI statements")]


class ApiKey(TimeStampedModel):
    name = models.CharField(max_length=120)
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.CASCADE,
                                    help_text="Scopes institution data to this organisation's members")
    prefix = models.CharField(max_length=12, unique=True)
    key_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @staticmethod
    def hash(raw):
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def generate(cls, **kwargs):
        prefix = "siq_" + secrets.token_hex(4)
        raw = f"{prefix}.{secrets.token_urlsafe(32)}"
        obj = cls.objects.create(prefix=prefix, key_hash=cls.hash(raw), **kwargs)
        return obj, raw


EVENTS = [("enrolment.created", "Enrolment created"), ("enrolment.completed", "Course completed"),
          ("credential.issued", "Credential issued"), ("credential.status_changed", "Credential suspended/revoked/reinstated"),
          ("exam.result_released", "Exam result released")]


class Webhook(TimeStampedModel):
    url = models.URLField()
    events = models.JSONField(default=list)
    secret = models.CharField(max_length=64, default=secrets.token_hex)
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.CASCADE,
                                    help_text="Only send events about this institution's members")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.url


class WebhookDelivery(models.Model):
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(max_length=40)
    payload = models.JSONField()
    status_code = models.PositiveSmallIntegerField(null=True)
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class XAPIStatement(models.Model):
    """Minimal Learning Record Store for xAPI statements (from SCORM/xAPI content and external tools)."""

    statement_id = models.UUIDField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.JSONField()
    verb = models.CharField(max_length=255, db_index=True)
    object_id = models.CharField(max_length=500, db_index=True)
    result = models.JSONField(null=True, blank=True)
    raw = models.JSONField()
    stored_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["-stored_at"]


class ScormPackage(TimeStampedModel):
    lesson = models.OneToOneField("catalog.Lesson", on_delete=models.CASCADE, related_name="scorm")
    package = models.FileField(upload_to="scorm/zips/")
    version = models.CharField(max_length=10, default="1.2")
    launch_path = models.CharField(max_length=255, blank=True)
    extracted_dir = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=255, blank=True)


class ScormAttempt(TimeStampedModel):
    package = models.ForeignKey(ScormPackage, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    cmi = models.JSONField(default=dict)
    completed = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = [("package", "user")]


class LtiPlatform(TimeStampedModel):
    """An LMS (e.g. a university Moodle) that launches SportIQ courses via LTI 1.3."""

    name = models.CharField(max_length=120)
    issuer = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    deployment_id = models.CharField(max_length=255, blank=True)
    auth_login_url = models.URLField()
    jwks_url = models.URLField()
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("issuer", "client_id")]

    def __str__(self):
        return self.name


class ExternalIdentity(models.Model):
    """Links a SportIQ account to an SSO / LTI identity."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_identities")
    provider = models.CharField(max_length=60)
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("provider", "subject")]


class RegistryAdapterLog(models.Model):
    """Calls to federation registries / identity services (Phase 4), logged for audit."""

    adapter = models.CharField(max_length=60)
    action = models.CharField(max_length=60)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    request_summary = models.CharField(max_length=255)
    outcome = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
