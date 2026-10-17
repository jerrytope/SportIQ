import io
import qrcode
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from apps.core.audit import audit
from apps.core.models import add_months
from apps.notifications.services import notify

from .models import Credential, CredentialEvent, CredentialType

GREEN = colors.HexColor("#008751")
DEEP = colors.HexColor("#0B3D2E")
GOLD = colors.HexColor("#F2C230")
MUTED = colors.HexColor("#6B7A72")


def default_completion_type():
    ct, _ = CredentialType.objects.get_or_create(
        code="course-completion",
        defaults={"name": "Certificate of Completion", "kind": CredentialType.COMPLETION},
    )
    return ct


@transaction.atomic
def issue(user, credential_type, title, course=None, actor=None, grade=""):
    expires = None
    if credential_type.validity_months:
        expires = add_months(timezone.now(), credential_type.validity_months)
    cred = Credential.objects.create(
        user=user, credential_type=credential_type, course=course,
        course_version=course.version if course else None, title=title,
        holder_name=user.get_full_name() or user.email, grade=grade, expires_at=expires, issued_by=actor,
    )
    CredentialEvent.objects.create(credential=cred, action="issued", actor=actor)
    audit(actor, "credential.issued", cred, {"user": user.email, "type": credential_type.code})
    from apps.integrations.services import emit

    transaction.on_commit(lambda: emit("credential.issued", user, {
        "code": cred.code, "title": cred.title, "type": credential_type.code, "kind": credential_type.kind,
        "holder": cred.holder_name, "issued_at": cred.issued_at.isoformat(),
        "expires_at": cred.expires_at.isoformat() if cred.expires_at else None}))
    notify(user, f"Certificate issued: {title}",
           f"Your {credential_type.name.lower()} is ready. Verification code: {cred.code}",
           cred.get_absolute_url(), sms=True)
    return cred


def issue_for_enrolment(enrolment):
    course = enrolment.course
    existing = Credential.objects.filter(user=enrolment.user, course=course).exclude(status=Credential.REVOKED).first()
    if existing:
        return existing
    ctype = course.credential_type or default_completion_type()
    grade = ""
    exam = course.final_exam()
    if exam:
        best = exam.attempts.filter(user=enrolment.user, passed=True).order_by("-percent").first()
        if best:
            grade = f"{best.percent}%"
    return issue(enrolment.user, ctype, course.title, course=course, grade=grade)


def change_status(cred, status, reason, actor, request=None):
    action = {"active": "reinstated", "suspended": "suspended", "revoked": "revoked"}[status]
    old = cred.status
    cred.status = status
    cred.status_reason = reason
    cred.save(update_fields=["status", "status_reason", "updated_at"])
    CredentialEvent.objects.create(credential=cred, action=action, note=reason, actor=actor)
    audit(actor, f"credential.{action}", cred, {"from": old, "to": status, "reason": reason}, request)
    from apps.integrations.services import emit

    emit("credential.status_changed", cred.user, {"code": cred.code, "status": status, "reason": reason})
    notify(cred.user, f"Credential {action}: {cred.title}", reason or "", cred.get_absolute_url())


def qr_png(data):
    img = qrcode.make(data, box_size=8, border=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def verify_url(cred):
    return f"{settings.SITE_URL}{cred.get_verify_url()}"


def render_pdf(cred):
    buf = io.BytesIO()
    w, h = landscape(A4)
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setTitle(f"{cred.title} — {cred.holder_name}")
    # Frame
    c.setFillColor(colors.white)
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(0, 0, 28, h, fill=1, stroke=0)
    c.rect(w - 28, 0, 28, h, fill=1, stroke=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.rect(48, 30, w - 96, h - 60, fill=0, stroke=1)
    # Header
    c.setFillColor(DEEP)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(72, h - 80, "SportIQ")
    c.setFont("Helvetica", 10)
    c.setFillColor(MUTED)
    c.drawString(72, h - 96, "NIS Digital Sports Academy  ·  National Institute for Sports, Nigeria")
    c.setFillColor(GREEN)
    c.roundRect(w - 300, h - 98, 228, 26, 13, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(w - 186, h - 89, cred.credential_type.get_kind_display().upper())
    # Body
    c.setFillColor(DEEP)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(w / 2, h - 175, cred.credential_type.name)
    c.setFont("Helvetica", 13)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, h - 210, "This is to certify that")
    c.setFillColor(DEEP)
    c.setFont("Times-BoldItalic", 34)
    c.drawCentredString(w / 2, h - 255, cred.holder_name)
    c.setStrokeColor(GOLD)
    c.line(w / 2 - 200, h - 268, w / 2 + 200, h - 268)
    c.setFont("Helvetica", 13)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, h - 295, "has successfully completed")
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, h - 325, cred.title[:70])
    if cred.grade:
        c.setFont("Helvetica", 11)
        c.setFillColor(MUTED)
        c.drawCentredString(w / 2, h - 345, f"Final assessment score: {cred.grade}")
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, h - 368, cred.credential_type.explainer[:150])
    # Footer details
    c.setFillColor(DEEP)
    c.setFont("Helvetica", 10)
    y = 110
    c.drawString(72, y, f"Issued: {timezone.localtime(cred.issued_at):%d %B %Y}")
    c.drawString(72, y - 16, "Expires: " + (f"{timezone.localtime(cred.expires_at):%d %B %Y}" if cred.expires_at else "Does not expire"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y - 38, f"Verification code: {cred.code}")
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawString(72, y - 54, f"Verify at {verify_url(cred)}")
    c.setStrokeColor(DEEP)
    c.line(w / 2 - 90, y - 10, w / 2 + 90, y - 10)
    c.setFillColor(DEEP)
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, y - 24, "Registrar, National Institute for Sports")
    c.drawImage(ImageReader(qr_png(verify_url(cred))), w - 182, 58, 104, 104)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


# --- Phase 2: CPD, programmes, renewals, prior learning -----------------------------------

def record_cpd(user, title, kind, hours, source_key, provider="SportIQ"):
    """Automatic, pre-approved CPD for activity completed on SportIQ (idempotent per source_key)."""
    from decimal import Decimal

    from .models import CPDActivity

    obj, created = CPDActivity.objects.get_or_create(
        user=user, source_key=source_key,
        defaults={"title": title, "kind": kind, "hours": hours, "points": Decimal(str(hours)), "status": "approved",
                  "provider": provider},
    )
    return obj


def cpd_points(user, since=None):
    from django.db.models import Sum

    qs = user.cpd_activities.filter(status="approved")
    if since:
        qs = qs.filter(date__gte=since)
    return qs.aggregate(s=Sum("points"))["s"] or 0


def programme_progress(user, programme):
    done = set(user.enrolments.filter(status="completed").values_list("course_id", flat=True))
    courses = [{"course": c, "done": c.pk in done} for c in programme.courses.all()]
    from apps.practicals.models import Submission

    tasks = []
    for t in programme.practical_tasks.all():
        passed = Submission.objects.filter(task=t, user=user, status="passed", supervisor_signed_at__isnull=False).exists() \
            if t.requires_supervisor else Submission.objects.filter(task=t, user=user, status="passed").exists()
        tasks.append({"task": t, "done": passed})
    total = len(courses) + len(tasks)
    complete = sum(i["done"] for i in courses + tasks)
    return {"courses": courses, "tasks": tasks, "pct": round(100 * complete / total) if total else 0,
            "complete": total > 0 and complete == total}


def check_programmes(user):
    """Award any NIS qualification whose requirements the user has now met."""
    from .models import Programme

    awarded = []
    for p in Programme.objects.filter(is_published=True).prefetch_related("courses", "practical_tasks"):
        if Credential.objects.filter(user=user, credential_type=p.credential_type, title=p.title).exclude(status="revoked").exists():
            continue
        if p.requires_application and not user.applications.filter(course__in=p.courses.all(), status="admitted").exists() \
                and not p.programme_applications_ok(user):
            continue
        if programme_progress(user, p)["complete"]:
            awarded.append(issue(user, p.credential_type, p.title))
    return awarded


def renew(cred, actor, note=""):
    cred.expires_at = add_months(max(cred.expires_at or timezone.now(), timezone.now()), cred.credential_type.validity_months)
    if cred.status == Credential.SUSPENDED and "expired" in (cred.status_reason or ""):
        cred.status = Credential.ACTIVE
    cred.save(update_fields=["expires_at", "status"])
    CredentialEvent.objects.create(credential=cred, action="renewed", note=note, actor=actor)
    audit(actor, "credential.renewed", cred, {"expires": cred.expires_at.isoformat()})
    notify(cred.user, f"Credential renewed: {cred.title}", f"Valid until {cred.expires_at:%d %b %Y}.", cred.get_absolute_url())


def open_badge(cred, request):
    """Open Badges 3.0 (Verifiable Credential) JSON-LD representation (unsigned; verification via the hosted URL)."""
    base = request.build_absolute_uri("/").rstrip("/")
    return {
        "@context": ["https://www.w3.org/ns/credentials/v2", "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json"],
        "id": f"{base}{cred.get_verify_url()}",
        "type": ["VerifiableCredential", "OpenBadgeCredential"],
        "issuer": {"id": base, "type": ["Profile"], "name": cred.credential_type.issuer_name},
        "validFrom": cred.issued_at.isoformat(),
        "validUntil": cred.expires_at.isoformat() if cred.expires_at else None,
        "name": cred.title,
        "credentialSubject": {
            "type": ["AchievementSubject"], "name": cred.holder_name,
            "achievement": {
                "id": f"{base}/credentials/types/{cred.credential_type.code}",
                "type": ["Achievement"], "name": cred.title,
                "achievementType": {"completion": "Certificate", "competence": "Competency",
                                    "qualification": "Certificate", "licence": "License"}[cred.credential_type.kind],
                "description": cred.credential_type.explainer,
                "criteria": {"narrative": cred.course.assessment_criteria if cred.course else cred.credential_type.description},
            },
        },
        "credentialStatus": {"type": "SportIQHostedStatus", "status": cred.effective_status},
    }
