import base64
import io

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.audit import client_ip

from . import services
from .models import Credential, VerificationLog


@login_required
def wallet(request):
    creds = request.user.credentials.select_related("credential_type", "course")
    return render(request, "credentials/wallet.html", {"credentials": creds})


@login_required
def detail(request, pk):
    cred = get_object_or_404(Credential.objects.select_related("credential_type"), pk=pk)
    if cred.user != request.user and not request.user.has_role("registrar"):
        raise Http404
    qr = base64.b64encode(services.qr_png(services.verify_url(cred)).getvalue()).decode()
    return render(request, "credentials/detail.html", {
        "cred": cred, "qr": f"data:image/png;base64,{qr}", "verify_url": services.verify_url(cred),
        "events": cred.events.all()[:10], "verifications": cred.verifications.count(),
    })


@login_required
def pdf(request, pk):
    cred = get_object_or_404(Credential, pk=pk)
    if cred.user != request.user and not request.user.has_role("registrar"):
        raise Http404
    if cred.status == Credential.REVOKED and not request.user.has_role("registrar"):
        raise Http404
    return FileResponse(services.render_pdf(cred), as_attachment=True, filename=f"SportIQ-{cred.code}.pdf",
                        content_type="application/pdf")


@login_required
def transcript(request):
    """Digital transcript: completed courses, results and credentials."""
    user = request.user
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            title=f"SportIQ transcript — {user.get_full_name()}")
    ss = getSampleStyleSheet()
    green = colors.HexColor("#008751")
    story = [Paragraph("<font color='#0B3D2E' size=18><b>SportIQ</b></font> &nbsp; Academic transcript", ss["Title"]),
             Paragraph(f"{user.get_full_name()} · {user.email} · generated {timezone.localdate():%d %B %Y}", ss["Normal"]),
             Spacer(1, 8 * mm), Paragraph("Completed courses", ss["Heading2"])]
    rows = [["Course", "Level", "Completed", "Best result"]]
    for e in user.enrolments.filter(status="completed").select_related("course"):
        exam = e.course.final_exam()
        best = exam.attempts.filter(user=user, status="released").order_by("-percent").first() if exam else None
        rows.append([Paragraph(e.course.title, ss["Normal"]), e.course.get_level_display(),
                     e.completed_at.strftime("%d %b %Y") if e.completed_at else "", f"{best.percent}%" if best else "—"])
    style = TableStyle([("BACKGROUND", (0, 0), (-1, 0), green), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E3EBE6")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9)])
    story.append(Table(rows if len(rows) > 1 else rows + [["No completed courses", "", "", ""]],
                       colWidths=[85 * mm, 28 * mm, 30 * mm, 30 * mm], style=style))
    story += [Spacer(1, 8 * mm), Paragraph("Credentials", ss["Heading2"])]
    crow = [["Credential", "Type", "Code", "Status"]]
    for c in user.credentials.select_related("credential_type"):
        crow.append([Paragraph(c.title, ss["Normal"]), c.credential_type.get_kind_display(), c.code,
                     c.effective_status.title()])
    story.append(Table(crow if len(crow) > 1 else crow + [["None", "", "", ""]],
                       colWidths=[70 * mm, 45 * mm, 32 * mm, 26 * mm], style=style))
    story += [Spacer(1, 8 * mm), Paragraph(
        "Each credential can be verified at sportiq.edu.ng/verify. A course completion certificate is not a "
        "professional licence.", ss["Italic"])]
    doc.build(story)
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename="SportIQ-transcript.pdf", content_type="application/pdf")


def _throttled(request):
    key = f"verify:{client_ip(request)}"
    n = cache.get(key, 0)
    cache.set(key, n + 1, 60)
    return n >= 30


def verify(request):
    code = (request.GET.get("code") or "").strip().upper()
    if code:
        return redirect("credentials:verify_code", code=code)
    return render(request, "credentials/verify.html")


def verify_code(request, code):
    code = code.strip().upper()
    if _throttled(request):
        return render(request, "credentials/verify.html", {"throttled": True, "code": code}, status=429)
    cred = Credential.objects.select_related("credential_type", "course").filter(code=code).first()
    VerificationLog.objects.create(credential=cred, query=code[:60], found=bool(cred), ip_address=client_ip(request),
                                   user_agent=request.META.get("HTTP_USER_AGENT", "")[:255])
    return render(request, "credentials/verify.html", {"cred": cred, "code": code, "searched": True})
