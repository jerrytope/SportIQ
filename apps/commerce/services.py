"""Paystack checkout. With no PAYSTACK_SECRET_KEY configured, a local test-mode page simulates the gateway."""
import hashlib
import hmac
import json
import urllib.request

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.audit import audit
from apps.learning.services import enrol
from apps.notifications.services import notify

from .models import Order, Refund

PAYSTACK = "https://api.paystack.co"


def live_mode():
    return bool(settings.PAYSTACK_SECRET_KEY)


def _paystack(method, path, body=None):
    req = urllib.request.Request(
        PAYSTACK + path, method=method, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def create_order(user, course, voucher=None):
    discount = 0
    if voucher and voucher.is_usable_for(course):
        discount = course.price_kobo * voucher.discount_percent // 100
    else:
        voucher = None
    return Order.objects.create(
        user=user, course=course, list_price_kobo=course.price_kobo, discount_kobo=discount,
        amount_kobo=course.price_kobo - discount, voucher=voucher,
    )


def checkout_url(order, callback_url):
    if not live_mode():
        return None
    data = _paystack("POST", "/transaction/initialize", {
        "email": order.user.email, "amount": order.amount_kobo, "reference": order.reference,
        "callback_url": callback_url, "metadata": {"course": order.course.slug},
    })
    return data["data"]["authorization_url"]


def verify_with_gateway(order):
    if not live_mode():
        return True
    data = _paystack("GET", f"/transaction/verify/{order.reference}")
    ok = data.get("data", {}).get("status") == "success" and data["data"]["amount"] == order.amount_kobo
    order.provider_payload = data.get("data", {})
    return ok


@transaction.atomic
def mark_paid(order, payload=None):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == Order.PAID:
        return order
    order.status = Order.PAID
    order.paid_at = timezone.now()
    if payload:
        order.provider_payload = payload
    order.save()
    if order.voucher_id:
        type(order.voucher).objects.filter(pk=order.voucher_id).update(times_used=F("times_used") + 1)
    source = "sponsored" if order.amount_kobo == 0 else "paid"
    enrol(order.user, order.course, source=source)
    notify(order.user, f"Payment received: {order.course.title}",
           f"Reference {order.reference}. Amount ₦{order.amount_naira:,.2f}.", "/account/payments/")
    return order


def valid_webhook(raw_body, signature):
    if not live_mode() or not signature:
        return False
    digest = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature)


@transaction.atomic
def refund(order, amount_kobo, reason, actor, request=None):
    if order.status != Order.PAID:
        raise ValueError("Only paid orders can be refunded")
    if live_mode():
        _paystack("POST", "/refund", {"transaction": order.reference, "amount": amount_kobo})
    r = Refund.objects.create(order=order, amount_kobo=amount_kobo, reason=reason, processed_by=actor)
    if amount_kobo >= order.amount_kobo:
        order.status = Order.REFUNDED
        order.save(update_fields=["status"])
    audit(actor, "payment.refunded", order, {"amount_kobo": amount_kobo, "reason": reason}, request)
    notify(order.user, "Refund processed", f"₦{amount_kobo / 100:,.2f} for {order.course.title}.", "/account/payments/")
    return r
