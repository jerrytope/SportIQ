from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Announcement(TimeStampedModel):
    AUDIENCES = [("all", "All learners"), ("profession", "A profession"), ("institution", "An institution's members"),
                 ("course", "Learners on a course"), ("staff", "Staff only")]
    title = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(max_length=12, choices=AUDIENCES, default="all")
    profession = models.ForeignKey("catalog.Profession", null=True, blank=True, on_delete=models.CASCADE)
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.CASCADE)
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Campaign(TimeStampedModel):
    """Targeted email/SMS message sent from the back office."""

    CHANNELS = [("email", "Email"), ("sms", "SMS"), ("inapp", "In-platform notification")]
    channel = models.CharField(max_length=6, choices=CHANNELS, default="email")
    subject = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(max_length=12, choices=Announcement.AUDIENCES, default="all")
    profession = models.ForeignKey("catalog.Profession", null=True, blank=True, on_delete=models.SET_NULL)
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.SET_NULL)
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.SET_NULL)
    sent_count = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class MessageLog(models.Model):
    channel = models.CharField(max_length=6)
    to = models.CharField(max_length=200)
    subject = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default="sent")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
