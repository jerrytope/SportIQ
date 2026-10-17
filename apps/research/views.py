from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.notifications.services import notify

from .models import Dataset, DatasetRequest, OutcomeSurvey, PeerReview, Project, Publication

ETHICS_ITEMS = [
    ("consent", "Participants give informed consent (parents/guardians and child assent for under-18s)"),
    ("minimise", "Only the data needed to answer the question is collected"),
    ("anonymise", "Data is anonymised or pseudonymised before analysis"),
    ("storage", "Data is stored securely and deleted on a stated date"),
    ("medical", "Medical or performance data is handled by qualified staff only"),
    ("withdraw", "Participants can withdraw without penalty"),
    ("ndpa", "Processing has a lawful basis under the Nigeria Data Protection Act 2023"),
]


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["title", "summary", "research_question", "methods", "institution", "involves_human_participants",
                  "involves_children", "uses_athlete_data", "recruiting"]
        widgets = {"summary": forms.Textarea(attrs={"rows": 3}), "research_question": forms.Textarea(attrs={"rows": 2}),
                   "methods": forms.Textarea(attrs={"rows": 4})}
        labels = {"recruiting": "Invite collaborators via the opportunities board"}


@login_required
def index(request):
    return render(request, "research/index.html", {
        "projects": Project.objects.filter(status__in=["active", "complete"]).select_related("lead")[:12],
        "mine": (Project.objects.filter(lead=request.user) | Project.objects.filter(members=request.user)).distinct(),
        "publications": Publication.objects.filter(status="published")[:10],
        "datasets": Dataset.objects.all(), "reviews": PeerReview.objects.filter(reviewer=request.user, submitted=False).select_related("publication"),
        "my_requests": {r.dataset_id: r for r in request.user.dataset_requests.all()},
    })


@login_required
def project_new(request):
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.lead = request.user
        p.ethics_checklist = {k: request.POST.get(f"ethics_{k}") == "on" for k, _ in ETHICS_ITEMS}
        p.status = "ethics" if p.involves_human_participants else "proposal"
        p.save()
        p.members.add(request.user)
        messages.success(request, "Proposal submitted to the NIS research office" + (" for ethics review." if p.status == "ethics" else "."))
        return redirect(p)
    return render(request, "research/project_form.html", {"form": form, "ethics": ETHICS_ITEMS})


def project(request, slug):
    p = get_object_or_404(Project.objects.select_related("lead"), slug=slug)
    is_member = request.user.is_authenticated and (p.members.filter(pk=request.user.pk).exists() or request.user.has_role("research_officer"))
    if p.status not in ("active", "complete") and not is_member:
        raise Http404
    if request.method == "POST" and request.user.is_authenticated and request.POST.get("action") == "join" and p.recruiting:
        notify(p.lead, f"{request.user} wants to join {p.title}", request.POST.get("note", "")[:300], p.get_absolute_url())
        messages.success(request, "Your interest has been sent to the project lead.")
        return redirect(p)
    return render(request, "research/project.html", {"p": p, "is_member": is_member, "ethics": [(l, p.ethics_checklist.get(k)) for k, l in ETHICS_ITEMS],
                                                     "base": "app/base.html" if request.user.is_authenticated else "public/base.html"})


@login_required
@require_POST
def dataset_request(request, pk):
    d = get_object_or_404(Dataset, pk=pk)
    if d.access == "open":
        return redirect("research:dataset_download", pk=pk)
    if request.POST.get("agree") != "on" or len(request.POST.get("purpose", "")) < 20:
        messages.error(request, "Describe your purpose (20+ characters) and accept the data-use terms.")
        return redirect("research:index")
    DatasetRequest.objects.get_or_create(dataset=d, user=request.user, defaults={
        "purpose": request.POST["purpose"][:3000], "agrees_to_terms": True,
        "project": Project.objects.filter(pk=request.POST.get("project"), members=request.user).first()})
    messages.success(request, "Request sent to the research office.")
    return redirect("research:index")


@login_required
def dataset_download(request, pk):
    d = get_object_or_404(Dataset, pk=pk)
    ok = d.access == "open" or request.user.has_role("research_officer") or DatasetRequest.objects.filter(
        dataset=d, user=request.user, status="approved").exclude(expires_on__lt=timezone.localdate()).exists()
    if not ok:
        raise Http404
    audit(request.user, "research.dataset_downloaded", d, request=request)
    return FileResponse(d.file.open("rb"), as_attachment=True, filename=d.file.name.split("/")[-1])


class PublicationForm(forms.ModelForm):
    class Meta:
        model = Publication
        fields = ["title", "kind", "authors", "abstract", "file", "project"]
        widgets = {"abstract": forms.Textarea(attrs={"rows": 5})}


@login_required
def publication_new(request):
    form = PublicationForm(request.POST or None, request.FILES or None)
    form.fields["project"].queryset = Project.objects.filter(members=request.user)
    if request.method == "POST" and form.is_valid():
        pub = form.save(commit=False)
        pub.submitted_by, pub.status = request.user, "review"
        pub.save()
        messages.success(request, "Submitted for peer review.")
        return redirect("research:index")
    return render(request, "research/publication_form.html", {"form": form})


def publication(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    if pub.status != "published" and not (request.user.is_authenticated and (pub.submitted_by == request.user or request.user.has_role("research_officer")
                                                                              or pub.reviews.filter(reviewer=request.user).exists())):
        raise Http404
    return render(request, "research/publication.html", {"pub": pub, "base": "app/base.html" if request.user.is_authenticated else "public/base.html"})


@login_required
def review(request, pk):
    rv = get_object_or_404(PeerReview.objects.select_related("publication"), pk=pk, reviewer=request.user)
    if request.method == "POST" and not rv.submitted:
        rec = request.POST.get("recommendation")
        if rec in dict(PeerReview.RECS):
            rv.recommendation, rv.comments, rv.submitted = rec, request.POST.get("comments", "")[:10000], True
            rv.save()
            messages.success(request, "Review submitted. Thank you.")
            return redirect("research:index")
    return render(request, "research/review.html", {"rv": rv, "recs": PeerReview.RECS})


@login_required
def outcome_survey(request, pk):
    s = get_object_or_404(OutcomeSurvey.objects.select_related("enrolment__course"), pk=pk, enrolment__user=request.user)
    if request.method == "POST" and not s.responded_at:
        try:
            s.applied_learning = max(1, min(5, int(request.POST.get("applied_learning", 3))))
        except ValueError:
            s.applied_learning = 3
        s.role_change = request.POST.get("role_change", "none") if request.POST.get("role_change") in dict(OutcomeSurvey._meta.get_field("role_change").choices) else "none"
        s.employed_in_sport = {"yes": True, "no": False}.get(request.POST.get("employed"))
        s.comment = request.POST.get("comment", "")[:3000]
        s.consent_research = request.POST.get("consent") == "on"
        s.responded_at = timezone.now()
        s.save()
        messages.success(request, "Thank you. This helps NIS show the real impact of training.")
        return redirect("learning:dashboard")
    return render(request, "research/outcome_survey.html", {"s": s, "roles": OutcomeSurvey._meta.get_field("role_change").choices})
