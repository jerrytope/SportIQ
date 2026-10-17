from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.notifications.services import notify

from .models import LiveSession, OfficeHourSlot, Poll, PollVote, Registration, SessionQuestion


def _visible(user):
    enrolled = user.enrolments.values("course_id")
    return LiveSession.objects.filter(Q(is_public=True) | Q(course_id__in=enrolled) | Q(host=user) | Q(co_hosts=user)).distinct()


def _is_host(user, s):
    return s.host_id == user.pk or s.co_hosts.filter(pk=user.pk).exists() or user.has_role("academic_manager")


@login_required
def index(request):
    now = timezone.now()
    qs = _visible(request.user).exclude(status="cancelled").select_related("course", "host")
    mine = set(request.user.live_registrations.values_list("session_id", flat=True))
    return render(request, "live/index.html", {
        "upcoming": qs.filter(starts_at__gte=now - timezone.timedelta(hours=3)).order_by("starts_at")[:30],
        "recordings": qs.filter(starts_at__lt=now).exclude(recording_url="").order_by("-starts_at")[:12],
        "mine": mine,
        "slots": OfficeHourSlot.objects.filter(starts_at__gte=now, booked_by__isnull=True).select_related("host", "course")[:12],
        "my_slots": request.user.booked_office_hours.filter(starts_at__gte=now - timezone.timedelta(hours=1)),
    })


@login_required
def detail(request, pk):
    s = get_object_or_404(_visible(request.user), pk=pk)
    reg = Registration.objects.filter(session=s, user=request.user).first()
    host = _is_host(request.user, s)
    return render(request, "live/detail.html", {
        "s": s, "reg": reg, "host": host, "count": s.registrations.count(),
        "polls": s.polls.prefetch_related("votes"), "voted": set(PollVote.objects.filter(poll__session=s, user=request.user).values_list("poll_id", flat=True)),
        # Attendees see approved questions plus their own awaiting approval; the host sees everything.
        "questions": s.questions.filter(Q(is_approved=True) | Q(user=request.user), is_hidden=False)
        .annotate(n=Count("upvotes")).order_by("is_answered", "-n", "-created_at")
        if not host else s.questions.annotate(n=Count("upvotes")).order_by("is_approved", "is_answered", "-n"),
        "attendees": s.registrations.select_related("user") if host else None,
    })


@login_required
@require_POST
def register(request, pk):
    s = get_object_or_404(_visible(request.user), pk=pk)
    if s.capacity and s.registrations.count() >= s.capacity:
        messages.error(request, "This session is full.")
    else:
        Registration.objects.get_or_create(session=s, user=request.user)
        notify(request.user, f"Registered: {s.title}", f"{timezone.localtime(s.starts_at):%a %d %b, %H:%M} WAT", s.get_absolute_url())
        messages.success(request, "You're registered. We'll remind you before it starts.")
    return redirect(s)


@login_required
@require_POST
def join(request, pk):
    s = get_object_or_404(_visible(request.user), pk=pk)
    if not s.is_live and not _is_host(request.user, s):
        messages.info(request, "The room opens 15 minutes before the start time.")
        return redirect(s)
    if s.record and request.POST.get("consent") != "on" and not _is_host(request.user, s):
        messages.error(request, "This session is recorded. Tick the box to agree before joining, or watch the recording later.")
        return redirect(s)
    reg, _ = Registration.objects.get_or_create(session=s, user=request.user)
    if not reg.attended:
        reg.attended, reg.joined_at, reg.recording_consent = True, timezone.now(), s.record
        reg.save()
        from apps.credentials.services import record_cpd

        record_cpd(request.user, f"Live: {s.title}", "live", s.cpd_points, f"live:{s.pk}")
    return render(request, "live/room.html", {"s": s})


@login_required
@require_POST
def ask(request, pk):
    s = get_object_or_404(_visible(request.user), pk=pk)
    text = request.POST.get("text", "").strip()
    if text:
        host = _is_host(request.user, s)
        SessionQuestion.objects.create(session=s, user=request.user, text=text[:500], is_approved=host)
        if not host:
            messages.info(request, "Thanks. Your question will appear once the host approves it.")
    return redirect(f"{s.get_absolute_url()}#qa")


@login_required
@require_POST
def question_action(request, qid):
    q = get_object_or_404(SessionQuestion, pk=qid)
    action = request.POST.get("action")
    if action == "upvote" and q.is_approved:
        q.upvotes.add(request.user)
    elif _is_host(request.user, q.session) and action in ("approve", "answered", "hide"):
        if action == "approve":
            q.is_approved = True
        elif action == "answered":
            q.is_answered = True
        else:
            q.is_hidden = True
        q.save()
    return redirect(f"{q.session.get_absolute_url()}#qa")


@login_required
@require_POST
def poll_create(request, pk):
    s = get_object_or_404(LiveSession, pk=pk)
    if not _is_host(request.user, s):
        raise Http404
    options = [o.strip() for o in request.POST.get("options", "").splitlines() if o.strip()]
    if request.POST.get("question") and len(options) >= 2:
        Poll.objects.create(session=s, question=request.POST["question"][:255], options=options[:8])
    return redirect(f"{s.get_absolute_url()}#polls")


@login_required
@require_POST
def vote(request, poll_id):
    poll = get_object_or_404(Poll, pk=poll_id, is_open=True)
    try:
        option = int(request.POST.get("option"))
    except (TypeError, ValueError):
        option = -1
    if 0 <= option < len(poll.options):
        PollVote.objects.get_or_create(poll=poll, user=request.user, defaults={"option": option})
    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse({"results": poll.results()})
    return redirect(f"{poll.session.get_absolute_url()}#polls")


@login_required
@require_POST
def book_slot(request, slot_id):
    slot = get_object_or_404(OfficeHourSlot, pk=slot_id, booked_by__isnull=True, starts_at__gte=timezone.now())
    slot.booked_by = request.user
    slot.topic = request.POST.get("topic", "")[:255]
    slot.save()
    notify(slot.host, "Office hour booked", f"{request.user} · {timezone.localtime(slot.starts_at):%d %b %H:%M} · {slot.topic}", "/live/", email=True)
    notify(request.user, "Office hour booked", f"With {slot.host} at {timezone.localtime(slot.starts_at):%d %b %H:%M}", "/live/")
    messages.success(request, "Booked. The join link is on this page.")
    return redirect("live:index")
