from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.catalog.models import Profession, Sport
from apps.notifications.services import notify

from .models import (ContentReport, Discussion, Group, GroupMember, MentorProfile, MentorshipRequest, Opportunity,
                     OpportunityApplication, Reply)


def _member(user, group):
    return GroupMember.objects.filter(group=group, user=user, approved=True).first()


def _can_moderate(user, group):
    return user.has_role("community_moderator") or GroupMember.objects.filter(group=group, user=user, role="moderator").exists()


@login_required
def home(request):
    mine = Group.objects.filter(groupmember__user=request.user, groupmember__approved=True)
    return render(request, "community/home.html", {
        "mine": mine, "groups": Group.objects.annotate(n=Count("members")).exclude(pk__in=mine)[:12],
        "opportunities": Opportunity.objects.filter(status="open").filter(Q(closes_on__isnull=True) | Q(closes_on__gte=timezone.localdate()))[:5],
        "recent": Discussion.objects.filter(group__in=mine, is_hidden=False).select_related("group", "author")[:10],
        "mentor_count": MentorProfile.objects.filter(approved=True, is_available=True).count(),
    })


@login_required
def group(request, slug):
    g = get_object_or_404(Group, slug=slug)
    member = _member(request.user, g)
    pending = GroupMember.objects.filter(group=g, user=request.user, approved=False).exists()
    mod = _can_moderate(request.user, g)
    if request.method == "POST" and member:
        if g.verified_only and not request.user.is_verified_professional:
            messages.error(request, "Only verified professionals can post in this group.")
        elif request.POST.get("title", "").strip() and request.POST.get("body", "").strip():
            d = Discussion.objects.create(group=g, author=request.user, title=request.POST["title"][:200], body=request.POST["body"][:10000])
            return redirect("community:discussion", pk=d.pk)
        return redirect(g)
    discussions = g.discussions.select_related("author").annotate(n=Count("replies"))
    if not mod:
        discussions = discussions.filter(is_hidden=False)
    return render(request, "community/group.html", {
        "g": g, "member": member, "pending": pending, "mod": mod, "discussions": discussions if (member or not g.is_private) else [],
        "count": g.groupmember_set.filter(approved=True).count(),
        "requests": g.groupmember_set.filter(approved=False).select_related("user") if mod else [],
    })


@login_required
@require_POST
def join(request, slug):
    g = get_object_or_404(Group, slug=slug)
    if g.course_id and not request.user.enrolments.filter(course=g.course, status="completed").exists():
        messages.error(request, "This alumni group is for people who have completed the course.")
        return redirect(g)
    m, created = GroupMember.objects.get_or_create(group=g, user=request.user, defaults={"approved": not g.is_private})
    if request.POST.get("leave") and not created:
        m.delete()
        messages.info(request, "You left the group.")
    elif created:
        messages.success(request, "Welcome to the group!" if m.approved else "Join request sent to the moderators.")
    return redirect(g)


@login_required
@require_POST
def approve_member(request, slug, user_id):
    g = get_object_or_404(Group, slug=slug)
    if not _can_moderate(request.user, g):
        raise Http404
    GroupMember.objects.filter(group=g, user_id=user_id).update(approved=request.POST.get("decision") == "approve")
    if request.POST.get("decision") != "approve":
        GroupMember.objects.filter(group=g, user_id=user_id).delete()
    return redirect(g)


@login_required
def discussion(request, pk):
    d = get_object_or_404(Discussion.objects.select_related("group", "author"), pk=pk)
    g = d.group
    member, mod = _member(request.user, g), _can_moderate(request.user, g)
    if (g.is_private and not member and not mod) or (d.is_hidden and not mod):
        raise Http404
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "reply" and member and request.POST.get("body", "").strip():
            if g.verified_only and not request.user.is_verified_professional:
                messages.error(request, "Only verified professionals can post here.")
            else:
                Reply.objects.create(discussion=d, author=request.user, body=request.POST["body"][:10000])
                if d.author != request.user:
                    notify(d.author, f"New reply: {d.title}", "", f"/community/discussions/{d.pk}/", email=False)
        elif mod and action in ("hide", "pin"):
            setattr(d, "is_hidden" if action == "hide" else "is_pinned", not getattr(d, "is_hidden" if action == "hide" else "is_pinned"))
            d.save()
        elif mod and action == "hide_reply":
            Reply.objects.filter(pk=request.POST.get("reply"), discussion=d).update(is_hidden=True)
        return redirect("community:discussion", pk=pk)
    replies = d.replies.select_related("author")
    if not mod:
        replies = replies.filter(is_hidden=False)
    return render(request, "community/discussion.html", {"d": d, "g": g, "replies": replies, "member": member, "mod": mod})


REPORTABLE = {"discussion": Discussion, "reply": Reply, "opportunity": Opportunity, "user": User}


@login_required
@require_POST
def report(request, kind, pk):
    model = REPORTABLE.get(kind)
    if not model:
        raise Http404
    obj = get_object_or_404(model, pk=pk)
    reason = request.POST.get("reason", "other")
    ContentReport.objects.create(reporter=request.user, content_type=ContentType.objects.get_for_model(model), object_id=obj.pk,
                                 reason=reason if reason in dict(ContentReport.REASONS) else "other", detail=request.POST.get("detail", "")[:2000])
    if reason == "safeguarding":
        messages.warning(request, "Thank you. For a safeguarding concern about a person, please also use the confidential integrity report so trained officers can act.")
    else:
        messages.success(request, "Thanks. A moderator will review this.")
    return redirect(request.META.get("HTTP_REFERER") or "community:home")


# --- Mentorship ---------------------------------------------------------------------------------

class MentorForm(forms.ModelForm):
    class Meta:
        model = MentorProfile
        fields = ["headline", "areas", "sports", "professions", "capacity", "is_available"]
        widgets = {"sports": forms.CheckboxSelectMultiple, "professions": forms.CheckboxSelectMultiple}


@login_required
def mentors(request):
    qs = MentorProfile.objects.filter(approved=True, is_available=True).select_related("user").prefetch_related("sports", "professions")
    if request.GET.get("sport"):
        qs = qs.filter(sports__slug=request.GET["sport"])
    if request.GET.get("profession"):
        qs = qs.filter(professions__slug=request.GET["profession"])
    mine = getattr(request.user, "mentor_profile", None)
    form = MentorForm(request.POST or None, instance=mine)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.user = request.user
        p.save()
        form.save_m2m()
        messages.success(request, "Mentor profile saved." + ("" if p.approved else " NIS will review it before it's listed."))
        return redirect("community:mentors")
    return render(request, "community/mentors.html", {
        "mentors": qs.exclude(user=request.user).distinct(), "form": form, "mine": mine,
        "my_requests": request.user.mentorship_requests.select_related("mentor__user"),
        "incoming": mine.requests.select_related("mentee") if mine else [],
        "sports": Sport.objects.all(), "professions": Profession.objects.all(),
    })


@login_required
@require_POST
def request_mentor(request, pk):
    m = get_object_or_404(MentorProfile, pk=pk, approved=True, is_available=True)
    if m.user == request.user or MentorshipRequest.objects.filter(mentor=m, mentee=request.user, status__in=["pending", "active"]).exists():
        return redirect("community:mentors")
    if m.active_mentees >= m.capacity:
        messages.error(request, "This mentor is at full capacity. Try another mentor.")
        return redirect("community:mentors")
    MentorshipRequest.objects.create(mentor=m, mentee=request.user, goals=request.POST.get("goals", "")[:2000])
    notify(m.user, "New mentorship request", f"{request.user}: {request.POST.get('goals', '')[:200]}", "/community/mentors/")
    messages.success(request, "Request sent.")
    return redirect("community:mentors")


@login_required
@require_POST
def mentorship_action(request, pk):
    r = get_object_or_404(MentorshipRequest, pk=pk)
    action = request.POST.get("action")
    if r.mentor.user == request.user and action in ("active", "declined", "completed"):
        r.status = action
        if request.POST.get("next_meeting_at"):
            r.next_meeting_at = request.POST["next_meeting_at"]
        r.save()
        notify(r.mentee, f"Mentorship {r.get_status_display().lower()}", f"with {r.mentor.user}", "/community/mentors/")
    elif r.mentee == request.user and action == "completed":
        r.status = "completed"
        r.save()
    return redirect("community:mentors")


# --- Opportunities ---------------------------------------------------------------------------------

class OpportunityForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["kind", "title", "organisation", "description", "requirements", "required_credential", "profession", "sport",
                  "state", "location", "paid", "closes_on", "apply_url"]
        widgets = {"closes_on": forms.DateInput(attrs={"type": "date"}), "description": forms.Textarea(attrs={"rows": 5}),
                   "requirements": forms.Textarea(attrs={"rows": 3})}


def opportunities(request):
    qs = Opportunity.objects.filter(status="open").filter(Q(closes_on__isnull=True) | Q(closes_on__gte=timezone.localdate()))
    for key, lookup in (("kind", "kind"), ("state", "state"), ("sport", "sport__slug"), ("profession", "profession__slug")):
        if request.GET.get(key):
            qs = qs.filter(**{lookup: request.GET[key]})
    from apps.research.models import Project

    return render(request, "community/opportunities.html", {
        "items": qs.select_related("sport", "profession"), "kinds": Opportunity.KINDS, "sports": Sport.objects.all(),
        "research": Project.objects.filter(recruiting=True, status="active")[:4],
        "base": "app/base.html" if request.user.is_authenticated else "public/base.html",
    })


def opportunity(request, pk):
    o = get_object_or_404(Opportunity, pk=pk)
    if o.status != "open" and not (request.user.is_authenticated and (o.posted_by == request.user or request.user.has_role("community_moderator"))):
        raise Http404
    applied = request.user.is_authenticated and o.applications.filter(user=request.user).first()
    eligible = True
    if o.required_credential_id and request.user.is_authenticated:
        eligible = request.user.credentials.filter(credential_type=o.required_credential, status="active").exists()
    if request.method == "POST" and request.user.is_authenticated and not applied and not o.apply_url:
        OpportunityApplication.objects.create(opportunity=o, user=request.user, cover_note=request.POST.get("cover_note", "")[:5000],
                                              share_profile=request.POST.get("share_profile") == "on")
        if o.posted_by:
            notify(o.posted_by, f"New application: {o.title}", str(request.user), f"/community/opportunities/{o.pk}/applicants/")
        messages.success(request, "Application sent.")
        return redirect(o)
    return render(request, "community/opportunity.html", {"o": o, "applied": applied, "eligible": eligible,
                                                          "base": "app/base.html" if request.user.is_authenticated else "public/base.html"})


@login_required
def post_opportunity(request):
    form = OpportunityForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        o = form.save(commit=False)
        o.posted_by = request.user
        admin_of = request.user.memberships.filter(role="admin").select_related("institution").first()
        o.institution = admin_of.institution if admin_of else None
        o.status = "open" if request.user.has_role("community_moderator") else "pending"
        o.save()
        messages.success(request, "Posted." if o.status == "open" else "Submitted. A moderator will approve it shortly.")
        return redirect("community:my_postings")
    return render(request, "community/post_opportunity.html", {"form": form})


@login_required
def my_postings(request):
    return render(request, "community/my_postings.html", {
        "postings": Opportunity.objects.filter(posted_by=request.user).annotate(n=Count("applications")),
        "applications": request.user.opportunity_applications.select_related("opportunity"),
    })


@login_required
def applicants(request, pk):
    o = get_object_or_404(Opportunity, pk=pk, posted_by=request.user)
    if request.method == "POST":
        OpportunityApplication.objects.filter(opportunity=o, pk=request.POST.get("app")).update(status=request.POST.get("status", "submitted"))
        return redirect("community:applicants", pk=pk)
    return render(request, "community/applicants.html", {"o": o, "apps": o.applications.select_related("user")})


def profile(request, user_id):
    """Public professional profile: only for people who opted in; only verified records shown."""
    person = get_object_or_404(User, pk=user_id, is_active=True, profile_public=True)
    return render(request, "community/profile.html", {
        "person": person, "credentials": person.credentials.filter(status="active").select_related("credential_type"),
        "experience": person.experience.all()[:8],
        "external": person.external_qualifications.filter(status="verified"),
        "base": "app/base.html" if request.user.is_authenticated else "public/base.html",
    })
