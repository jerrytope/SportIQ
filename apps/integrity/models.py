"""Confidential integrity & safeguarding reporting with restricted case management (blueprint Module 13).

Sensitive text is encrypted at rest (Fernet, key from INTEGRITY_ENCRYPTION_KEY) and visible only to
designated safeguarding officers — not to NIS or super administrators by default.
"""
import secrets

from django.conf import settings
from django.db import models

from apps.core.crypto import EncryptedTextField
from apps.core.models import TimeStampedModel


def make_reference():
    return "IR-" + secrets.token_hex(4).upper()


def make_access_code():
    return secrets.token_urlsafe(9)


class Report(TimeStampedModel):
    CATEGORIES = [("safeguarding", "Child safeguarding / abuse"), ("harassment", "Sexual harassment, bullying or discrimination"),
                  ("doping", "Doping"), ("manipulation", "Match-fixing / competition manipulation / betting"),
                  ("corruption", "Bribery, corruption or financial misconduct"), ("welfare", "Athlete welfare / mental health"),
                  ("other", "Other integrity concern")]
    STATUSES = [("new", "New"), ("triage", "Being assessed"), ("referred", "Referred to authority"),
                ("investigating", "Under investigation"), ("closed", "Closed")]
    reference = models.CharField(max_length=16, unique=True, default=make_reference)
    access_code = models.CharField(max_length=20, default=make_access_code, help_text="Lets an anonymous reporter check status")
    category = models.CharField(max_length=14, choices=CATEGORIES)
    anonymous = models.BooleanField(default=True)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+", help_text="Empty for anonymous reports")
    contact = EncryptedTextField(blank=True, help_text="Optional safe contact details")
    description = EncryptedTextField()
    people_involved = EncryptedTextField(blank=True)
    sport = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=40, blank=True)
    involves_child = models.BooleanField(default=False)
    immediate_danger = models.BooleanField(default=False)
    status = models.CharField(max_length=14, choices=STATUSES, default="new", db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="assigned_integrity_reports")
    public_update = models.CharField(max_length=255, blank=True, help_text="Status message the reporter can see")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference


class CaseNote(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = EncryptedTextField()
    action = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class CaseAccessLog(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="access_log")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
