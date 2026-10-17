import io

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from apps.learning.models import ActivityDay, LessonProgress

from .models import Challenge, ChallengeEntry, Experience


class ExperienceForm(forms.ModelForm):
    class Meta:
        model = Experience
        fields = ["role", "organisation", "sport", "level", "state", "start_date", "end_date", "description"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"}),
                   "description": forms.Textarea(attrs={"rows": 3})}


@login_required
def experience(request):
    edit = Experience.objects.filter(pk=request.GET.get("edit"), user=request.user).first()
    form = ExperienceForm(request.POST or None, instance=edit)
    if request.method == "POST":
        if request.POST.get("delete"):
            Experience.objects.filter(pk=request.POST["delete"], user=request.user).delete()
            return redirect("careers:experience")
        if form.is_valid():
            e = form.save(commit=False)
            e.user = request.user
            e.save()
            messages.success(request, "Experience saved.")
            return redirect("careers:experience")
    return render(request, "careers/experience.html", {"form": form, "items": request.user.experience.select_related("sport"), "edit": edit})


@login_required
def cv(request):
    """CV built from the learner's profile, experience and verified records only."""
    u = request.user
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, title=f"CV - {u.get_full_name()}")
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Heading2"], textColor=colors.HexColor("#008751"), spaceBefore=10)
    body = ss["Normal"]
    small = ParagraphStyle("s", parent=body, textColor=colors.HexColor("#6B7A72"), fontSize=8.5)
    story = [Paragraph(f"<b>{u.get_full_name()}</b>", ParagraphStyle("t", parent=ss["Title"], alignment=0, textColor=colors.HexColor("#0B3D2E"))),
             Paragraph(" · ".join(filter(None, [", ".join(p.name for p in u.professions.all()), ", ".join(s.name for s in u.sports.all()),
                                                 u.state, u.email, u.phone])), small),
             HRFlowable(color=colors.HexColor("#F2C230"), thickness=1.5, spaceBefore=6, spaceAfter=6)]
    if u.bio:
        story += [Paragraph("Profile", h), Paragraph(u.bio, body)]
    exp = list(u.experience.select_related("sport"))
    if exp:
        story.append(Paragraph("Experience", h))
        for e in exp:
            dates = f"{e.start_date:%b %Y} - " + (f"{e.end_date:%b %Y}" if e.end_date else "present")
            story.append(Paragraph(f"<b>{e.role}</b>, {e.organisation} <font color='#6B7A72'>({dates}; {e.get_level_display()}{'; ' + e.sport.name if e.sport else ''})</font>", body))
            if e.description:
                story.append(Paragraph(e.description, small))
            story.append(Spacer(1, 3))
    creds = list(u.credentials.filter(status="active").select_related("credential_type"))
    if creds:
        story.append(Paragraph("Qualifications &amp; certificates (verifiable)", h))
        for c in creds:
            story.append(Paragraph(f"<b>{c.title}</b>: {c.credential_type.get_kind_display()}, {c.credential_type.issuer_name}, {c.issued_at:%b %Y}. Verify: sportiq.edu.ng/verify/{c.code}", body))
    ext = list(u.external_qualifications.filter(status="verified"))
    if ext:
        story.append(Paragraph("Other qualifications (verified by NIS registrar)", h))
        for q in ext:
            story.append(Paragraph(f"<b>{q.title}</b>, {q.awarding_body}, {q.awarded_on:%b %Y}", body))
    pts = sum(a.points for a in u.cpd_activities.filter(status="approved"))
    if pts:
        story += [Paragraph("Continuing professional development", h), Paragraph(f"{pts} approved CPD points on SportIQ.", body)]
    if u.languages:
        story += [Paragraph("Languages", h), Paragraph(u.languages, body)]
    doc.build(story)
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename="CV.pdf", content_type="application/pdf")


def progress_for(challenge, user):
    start, end = challenge.starts_on, challenge.ends_on
    if challenge.metric == "lessons":
        return LessonProgress.objects.filter(enrolment__user=user, completed=True, completed_at__date__range=(start, end)).count()
    if challenge.metric == "courses":
        return user.enrolments.filter(status="completed", completed_at__date__range=(start, end)).count()
    if challenge.metric == "days":
        return ActivityDay.objects.filter(user=user, date__range=(start, end)).count()
    return user.practical_submissions.filter(status="passed", assessed_at__date__range=(start, end)).count()


@login_required
def challenges(request):
    today = timezone.localdate()
    qs = Challenge.objects.filter(is_active=True, ends_on__gte=today).filter(
        Q(cohort__isnull=True) | Q(cohort__enrolments__user=request.user)).distinct()
    joined = set(request.user.challenge_entries.values_list("challenge_id", flat=True))
    rows = [{"c": c, "joined": c.pk in joined, "progress": progress_for(c, request.user) if c.pk in joined else None} for c in qs]
    return render(request, "careers/challenges.html", {"rows": rows})


@login_required
def challenge(request, pk):
    c = get_object_or_404(Challenge, pk=pk, is_active=True)
    entry = ChallengeEntry.objects.filter(challenge=c, user=request.user).first()
    board = teams = None
    if c.show_leaderboard and (c.cohort is None or c.cohort.leaderboard_enabled):
        board = sorted(({"user": e.user, "n": progress_for(c, e.user)} for e in c.entries.select_related("user")),
                       key=lambda r: -r["n"])[:20]
    if c.team_mode:
        from apps.institutions.models import Institution

        teams = []
        for inst in Institution.objects.filter(memberships__user__challenge_entries__challenge=c).distinct():
            members = [e.user for e in c.entries.filter(user__memberships__institution=inst).select_related("user")]
            if members:
                teams.append({"team": inst.name, "members": len(members),
                              "avg": round(sum(progress_for(c, m) for m in members) / len(members), 1)})
        teams.sort(key=lambda t: -t["avg"])
    mine = progress_for(c, request.user) if entry else None
    return render(request, "careers/challenge.html", {"c": c, "entry": entry, "mine": mine, "board": board, "teams": teams,
                                                      "pct": min(100, round(100 * (mine or 0) / c.target)) if c.target else 0})


@login_required
@require_POST
def join_challenge(request, pk):
    c = get_object_or_404(Challenge, pk=pk, is_active=True)
    ChallengeEntry.objects.get_or_create(challenge=c, user=request.user)
    messages.success(request, "You've joined. Good luck!")
    return redirect("careers:challenge", pk=pk)
