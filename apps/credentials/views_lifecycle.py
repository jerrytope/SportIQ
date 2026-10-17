"""Phase 2 learner views: CPD, renewals, programmes (qualifications), prior learning, external quals, badges, portfolio."""
import io

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.catalog.models import Course
from apps.core.models import add_months
from apps.notifications.services import notify

from . import services
from .models import (CPDActivity, Credential, ExternalQualification, PriorLearningClaim, Programme, ProgrammeApplication,
                     RenewalRequest)


class CPDForm(forms.ModelForm):
    class Meta:
        model = CPDActivity
        fields = ["title", "kind", "provider", "date", "hours", "evidence", "reflection"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "reflection": forms.Textarea(attrs={"rows": 3})}


def cycle_start(cred):
    if not cred.expires_at or not cred.credential_type.validity_months:
        return None
    return add_months(cred.expires_at, -cred.credential_type.validity_months).date()


@login_required
def cpd(request):
    form = CPDForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        a = form.save(commit=False)
        a.user = request.user
        a.save()
        messages.success(request, "CPD activity logged. The registrar will review it and award points.")
        return redirect("credentials:cpd")
    rows = []
    for c in request.user.credentials.filter(status="active", credential_type__validity_months__isnull=False).select_related("credential_type"):
        pts = services.cpd_points(request.user, cycle_start(c))
        need = c.credential_type.cpd_points_for_renewal
        rows.append({"cred": c, "points": pts, "need": need, "ready": pts >= need,
                     "pending": c.renewal_requests.filter(status="pending").exists(),
                     "due_soon": bool(c.expires_at and c.expires_at <= timezone.now() + timezone.timedelta(days=120))})
    return render(request, "credentials/cpd.html", {
        "form": form, "activities": request.user.cpd_activities.all(), "total": services.cpd_points(request.user),
        "year": services.cpd_points(request.user, timezone.localdate().replace(month=1, day=1)), "renewals": rows,
    })


@login_required
@require_POST
def request_renewal(request, pk):
    cred = get_object_or_404(Credential, pk=pk, user=request.user, status="active")
    if cred.renewal_requests.filter(status="pending").exists():
        messages.info(request, "You already have a renewal request pending.")
    else:
        RenewalRequest.objects.create(credential=cred, cpd_points=services.cpd_points(request.user, cycle_start(cred)),
                                      note=request.POST.get("note", "")[:1000])
        messages.success(request, "Renewal requested. The registrar will check your CPD record.")
    return redirect("credentials:cpd")


@login_required
def programmes(request):
    items = [{"p": p, "progress": services.programme_progress(request.user, p)}
             for p in Programme.objects.filter(is_published=True).select_related("credential_type").prefetch_related("courses", "practical_tasks")]
    return render(request, "credentials/programmes.html", {"items": items})


class ProgrammeApplicationForm(forms.ModelForm):
    class Meta:
        model = ProgrammeApplication
        fields = ["statement", "document"]
        widgets = {"statement": forms.Textarea(attrs={"rows": 5})}


@login_required
def programme(request, slug):
    p = get_object_or_404(Programme, slug=slug, is_published=True)
    application = p.applications.filter(user=request.user).first()
    form = ProgrammeApplicationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and p.requires_application and not application and form.is_valid():
        a = form.save(commit=False)
        a.programme, a.user = p, request.user
        a.save()
        messages.success(request, "Application submitted.")
        return redirect(p)
    return render(request, "credentials/programme.html", {
        "p": p, "progress": services.programme_progress(request.user, p), "application": application, "form": form,
        "awarded": Credential.objects.filter(user=request.user, title=p.title, credential_type=p.credential_type).first(),
    })


class RPLForm(forms.ModelForm):
    class Meta:
        model = PriorLearningClaim
        fields = ["statement", "evidence"]
        widgets = {"statement": forms.Textarea(attrs={"rows": 6})}
        labels = {"evidence": "Evidence (certificate, transcript, employer letter)"}


@login_required
def rpl_claim(request, slug):
    course = get_object_or_404(Course.objects.published(), slug=slug)
    existing = PriorLearningClaim.objects.filter(user=request.user, course=course).first()
    form = RPLForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and not existing and form.is_valid():
        c = form.save(commit=False)
        c.user, c.course = request.user, course
        c.save()
        notify(request.user, f"Prior learning claim received: {course.title}", "An assessor will review your evidence.", "/credentials/")
        messages.success(request, "Claim submitted for review.")
        return redirect(course)
    return render(request, "credentials/rpl.html", {"course": course, "form": form, "existing": existing})


class ExternalQualForm(forms.ModelForm):
    class Meta:
        model = ExternalQualification
        fields = ["title", "awarding_body", "reference", "awarded_on", "expires_on", "evidence"]
        widgets = {"awarded_on": forms.DateInput(attrs={"type": "date"}), "expires_on": forms.DateInput(attrs={"type": "date"})}


@login_required
def external(request):
    form = ExternalQualForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        q = form.save(commit=False)
        q.user = request.user
        q.save()
        messages.success(request, "Submitted for verification. Verified qualifications appear on your profile.")
        return redirect("credentials:external")
    return render(request, "credentials/external.html", {"form": form, "items": request.user.external_qualifications.all()})


def badge_json(request, pk):
    cred = get_object_or_404(Credential.objects.select_related("credential_type", "course"), pk=pk)
    if cred.status == Credential.REVOKED:
        raise Http404
    resp = JsonResponse(services.open_badge(cred, request), json_dumps_params={"indent": 2})
    resp["Content-Type"] = "application/ld+json"
    return resp


@login_required
def portfolio(request):
    """Downloadable professional portfolio: profile, experience, credentials, external quals, practicals, CPD."""
    user = request.user
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            title=f"Professional portfolio - {user.get_full_name()}")
    ss = getSampleStyleSheet()
    style = TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#008751")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E3EBE6")), ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
    story = [Paragraph(f"<font color='#0B3D2E'>{user.get_full_name()}</font>", ss["Title"]),
             Paragraph(" · ".join(filter(None, [", ".join(p.name for p in user.professions.all()), user.state, user.email])), ss["Normal"]),
             Spacer(1, 4 * mm)]
    if user.bio:
        story.append(Paragraph(user.bio, ss["Normal"]))
    sections = [
        ("Experience", ["Role", "Organisation", "Level", "Dates"],
         [[e.role, e.organisation, e.get_level_display(),
           f"{e.start_date:%b %Y} - " + (f"{e.end_date:%b %Y}" if e.end_date else "present")] for e in user.experience.all()]),
        ("Credentials (verify at sportiq.edu.ng/verify)", ["Credential", "Type", "Code", "Status"],
         [[c.title, c.credential_type.get_kind_display(), c.code, c.effective_status.title()]
          for c in user.credentials.select_related("credential_type")]),
        ("Verified external qualifications", ["Qualification", "Awarding body", "Awarded"],
         [[q.title, q.awarding_body, f"{q.awarded_on:%b %Y}"] for q in user.external_qualifications.filter(status="verified")]),
        ("Practical evidence assessed as competent", ["Task", "Course", "Supervisor"],
         [[s.task.title, s.task.course.title, s.supervisor_name or "-"]
          for s in user.practical_submissions.filter(status="passed").select_related("task__course")]),
        ("CPD (approved)", ["Activity", "Date", "Points"],
         [[a.title, f"{a.date:%d %b %Y}", str(a.points)] for a in user.cpd_activities.filter(status="approved")[:40]]),
    ]
    for title, head, rows in sections:
        story += [Spacer(1, 6 * mm), Paragraph(title, ss["Heading2"])]
        if rows:
            story.append(Table([head] + [[Paragraph(str(c), ss["Normal"]) for c in r] for r in rows], style=style, repeatRows=1))
        else:
            story.append(Paragraph("None recorded.", ss["Italic"]))
    doc.build(story)
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename="SportIQ-portfolio.pdf", content_type="application/pdf")
