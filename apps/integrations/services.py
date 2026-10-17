import hashlib
import hmac
import json
import logging
import urllib.request
import uuid

from celery import shared_task
from django.utils import timezone

log = logging.getLogger("apps.integrations")


def emit(event, user, payload):
    """Queue webhook deliveries for an event. Institution-scoped hooks only fire for their own members."""
    from .models import Webhook

    hooks = [h for h in Webhook.objects.filter(is_active=True) if event in (h.events or [])]
    if not hooks:
        return 0
    member_of = set(user.memberships.values_list("institution_id", flat=True)) if user else set()
    body = {"id": str(uuid.uuid4()), "event": event, "created": timezone.now().isoformat(), "data": payload}
    n = 0
    for h in hooks:
        if h.institution_id and h.institution_id not in member_of:
            continue
        deliver.delay(h.pk, event, body)
        n += 1
    return n


@shared_task
def deliver(webhook_id, event, body):
    from .models import Webhook, WebhookDelivery

    h = Webhook.objects.get(pk=webhook_id)
    raw = json.dumps(body, default=str).encode()
    sig = hmac.new(h.secret.encode(), raw, hashlib.sha256).hexdigest()
    req = urllib.request.Request(h.url, data=raw, method="POST", headers={
        "Content-Type": "application/json", "X-SportIQ-Event": event, "X-SportIQ-Signature": f"sha256={sig}"})
    status, error = None, ""
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = resp.status
    except Exception as exc:  # noqa: BLE001 - recorded on the delivery for the admin to see
        error = str(exc)[:250]
        status = getattr(exc, "code", None)
    WebhookDelivery.objects.create(webhook=h, event=event, payload=body, status_code=status, error=error)
    return status
