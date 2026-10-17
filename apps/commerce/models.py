import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


def make_reference():
    return "SIQ" + timezone.now().strftime("%y%m%d") + secrets.token_hex(4).upper()


class Voucher(TimeStampedModel):
    """Scholarship / sponsored-seat code. 100% discount = sponsored enrolment."""

    code = models.CharField(max_length=30, unique=True)
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.CASCADE,
                               help_text="Empty = valid for any paid course")
    discount_percent = models.PositiveSmallIntegerField(default=100)
    max_uses = models.PositiveIntegerField(default=1)
    times_used = models.PositiveIntegerField(default=0)
    sponsor = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.SET_NULL)
    expires_on = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code

    def is_usable_for(self, course):
        if not self.is_active or self.times_used >= self.max_uses:
            return False
        if self.expires_on and self.expires_on < timezone.localdate():
            return False
        return self.course_id in (None, course.pk)


class Order(TimeStampedModel):
    PENDING, PAID, FAILED, REFUNDED = "pending", "paid", "failed", "refunded"
    STATUSES = [(PENDING, "Pending"), (PAID, "Paid"), (FAILED, "Failed"), (REFUNDED, "Refunded")]
    reference = models.CharField(max_length=40, unique=True, default=make_reference)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    course = models.ForeignKey("catalog.Course", on_delete=models.PROTECT, related_name="orders")
    list_price_kobo = models.PositiveIntegerField()
    discount_kobo = models.PositiveIntegerField(default=0)
    amount_kobo = models.PositiveIntegerField()
    voucher = models.ForeignKey(Voucher, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING, db_index=True)
    provider = models.CharField(max_length=20, default="paystack")
    provider_payload = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    reconciled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference

    @property
    def amount_naira(self):
        return self.amount_kobo / 100


class Refund(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    amount_kobo = models.PositiveIntegerField()
    reason = models.TextField()
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    @property
    def amount_naira(self):
        return self.amount_kobo / 100
