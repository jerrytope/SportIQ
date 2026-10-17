import json
import logging
import urllib.request

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from .models import Announcement, MessageLog, Notification

log = logging.getLogger("apps.notifications")


def send_email(to, subject, body):
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
        MessageLog.objects.create(channel="email", to=to, subject=subject[:200])
        return True
    except Exception as exc:  # noqa: BLE001 - logged and recorded, never breaks the request
        log.warning("email to %s failed: %s", to, exc)
        MessageLog.objects.create(channel="email", to=to, subject=subject[:200], status="failed")
        return False


def send_sms(phone, text):
    """Send via Termii when configured; otherwise log (dev)."""
    if not phone:
        return False
    if not settings.TERMII_API_KEY:
        log.info("[SMS dev] to %s: %s", phone, text)
        MessageLog.objects.create(channel="sms", to=phone, subject=text[:200], status="logged")
        return True
    payload = json.dumps({
        "to": phone, "from": settings.TERMII_SENDER_ID, "sms": text, "type": "plain",
        "channel": "generic", "api_key": settings.TERMII_API_KEY,
    }).encode()
    req = urllib.request.Request("https://api.ng.termii.com/api/sms/send", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        MessageLog.objects.create(channel="sms", to=phone, subject=text[:200])
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("sms to %s failed: %s", phone, exc)
        MessageLog.objects.create(channel="sms", to=phone, subject=text[:200], status="failed")
        return False


def notify(user, title, body="", url="", email=True, sms=False):
    """In-app notification plus email/SMS according to the user's preferences."""
    Notification.objects.create(user=user, title=title, body=body, url=url)
    if email and user.notify_email:
        link = f"\n\n{settings.SITE_URL}{url}" if url else ""
        send_email(user.email, f"SportIQ: {title}", f"{body}{link}")
    if sms and user.notify_sms and user.phone:
        send_sms(user.phone, f"SportIQ: {title}")


def announcements_for(user):
    qs = Announcement.objects.filter(is_active=True)
    if not user.is_authenticated:
        return qs.filter(audience="all")
    cond = Q(audience="all")
    cond |= Q(audience="profession", profession__in=user.professions.all())
    cond |= Q(audience="institution", institution__memberships__user=user)
    cond |= Q(audience="course", course__enrolments__user=user)
    if user.is_backoffice:
        cond |= Q(audience="staff")
    return qs.filter(cond).distinct()


def audience_users(obj):
    """Users targeted by an Announcement/Campaign-like object."""
    from apps.accounts.models import User

    qs = User.objects.filter(is_active=True)
    if obj.audience == "profession":
        qs = qs.filter(professions=obj.profession)
    elif obj.audience == "institution":
        qs = qs.filter(memberships__institution=obj.institution)
    elif obj.audience == "course":
        qs = qs.filter(enrolments__course=obj.course)
    elif obj.audience == "staff":
        qs = qs.exclude(staff_roles=[])
    return qs.distinct()


def send_campaign(campaign):
    count = 0
    for user in audience_users(campaign):
        if campaign.channel == "email":
            ok = send_email(user.email, campaign.subject, campaign.body)
        elif campaign.channel == "sms":
            ok = send_sms(user.phone, f"{campaign.subject}: {campaign.body}"[:300])
        else:
            Notification.objects.create(user=user, title=campaign.subject, body=campaign.body)
            ok = True
        count += int(bool(ok))
    campaign.sent_count = count
    campaign.sent_at = timezone.now()
    campaign.save(update_fields=["sent_count", "sent_at"])
    return count
