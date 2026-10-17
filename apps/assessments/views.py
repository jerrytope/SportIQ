import base64
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.learning.models import Enrolment
from apps.notifications.services import notify

from . import services
from .models import Appeal, Attempt, Exam, InvigilationSnapshot


@login_required
@require_POST
def start(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, is_published=True)
    if not Enrolment.objects.filter(user=request.user, course=exam.course, status__in=["active", "completed"]).exists():
        messages.error(request, "Enrol in the course to take this assessment.")
        return redirect(exam.course)
    if exam.identity_declaration and request.POST.get("declare") != "on":
        messages.error(request, "Please confirm the declaration (your identity and your own work) to start.")
        return redirect(request.META.get("HTTP_REFERER") or exam.course.get_absolute_url())
    try:
        attempt = services.start_attempt(exam, request.user)
    except services.ExamUnavailable as exc:
        messages.error(request, str(exc))
        return redirect(exam.course)
    if exam.webcam_invigilation and request.POST.get("alternative") == "on":
        attempt.accessible_alternative = True
        attempt.save(update_fields=["accessible_alternative"])
    return redirect("learning:attempt", pk=attempt.pk)


@login_required
def attempt(request, pk):
    att = get_object_or_404(Attempt.objects.select_related("exam", "exam__course"), pk=pk, user=request.user)
    if att.status == Attempt.IN_PROGRESS and not att.is_open:
        services.save_answers(att, request.POST) if request.method == "POST" else None
        services.submit_attempt(att, late=True)
        messages.info(request, "Time ran out, so your answers were submitted automatically.")
        return redirect("learning:attempt", pk=pk)
    if request.method == "POST" and att.status == Attempt.IN_PROGRESS:
        services.save_answers(att, request.POST)
        services.submit_attempt(att)
        att.refresh_from_db()
        if att.status == Attempt.RELEASED:
            messages.success(request, f"Submitted. You scored {att.percent}%.")
        else:
            messages.success(request, "Submitted. Your written answers will be marked by an examiner.")
        return redirect("learning:attempt", pk=pk)
    responses = att.responses.select_related("question").prefetch_related("question__choices", "selected")
    return render(request, "learning/attempt.html", {
        "attempt": att, "exam": att.exam, "responses": responses,
        "selected": {r.pk: set(r.selected.values_list("pk", flat=True)) for r in responses},
        "review": att.status != Attempt.IN_PROGRESS, "released": att.status == Attempt.RELEASED,
        "lesson": att.exam.lessons.first(), "appeal": att.appeals.first(),
        "webcam": att.exam.webcam_invigilation and not att.accessible_alternative,
    })


@login_required
@require_POST
def autosave(request, pk):
    att = get_object_or_404(Attempt, pk=pk, user=request.user, status=Attempt.IN_PROGRESS)
    if att.is_open:
        services.save_answers(att, request.POST)
        if request.POST.get("_offline_sync"):
            att.integrity_flags = list(att.integrity_flags) + ["answers synced after connection loss"]
            att.save(update_fields=["integrity_flags"])
    return JsonResponse({"ok": True, "seconds_left": att.seconds_left})


@login_required
@require_POST
def flag(request, pk):
    att = get_object_or_404(Attempt, pk=pk, user=request.user, status=Attempt.IN_PROGRESS)
    flags = list(att.integrity_flags)
    if len(flags) < 50:
        flags.append(request.POST.get("flag", "event")[:60])
        att.integrity_flags = flags
        att.save(update_fields=["integrity_flags"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def snapshot(request, pk):
    """Webcam invigilation frame (JPEG data URL). Only for exams that enable it, with consent given at start."""
    att = get_object_or_404(Attempt, pk=pk, user=request.user, status=Attempt.IN_PROGRESS, exam__webcam_invigilation=True)
    data = request.POST.get("image", "")
    if not data.startswith("data:image/jpeg;base64,") or len(data) > 400_000 or att.snapshots.count() >= 120:
        return HttpResponseBadRequest()
    snap = InvigilationSnapshot(attempt=att)
    snap.image.save(f"{att.pk}-{uuid.uuid4().hex[:8]}.jpg", ContentFile(base64.b64decode(data.split(",", 1)[1])), save=True)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def appeal(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    kind = request.POST.get("kind", "result")
    reason = request.POST.get("reason", "").strip()
    if kind not in dict(Appeal.KINDS) or len(reason) < 10:
        messages.error(request, "Please explain your request (at least a sentence).")
        return redirect(request.META.get("HTTP_REFERER") or exam.course.get_absolute_url())
    att = Attempt.objects.filter(pk=request.POST.get("attempt"), user=request.user, exam=exam).first()
    if Appeal.objects.filter(user=request.user, exam=exam, kind=kind, status="open").exists():
        messages.info(request, "You already have an open request for this assessment.")
    else:
        Appeal.objects.create(user=request.user, exam=exam, attempt=att, kind=kind, reason=reason[:4000])
        for i in exam.course.instructors.all():
            notify(i, f"New {dict(Appeal.KINDS)[kind].lower()}", f"{request.user} · {exam.title}", "/manage/assessments/appeals/", email=False)
        messages.success(request, "Request submitted. You'll be notified of the outcome.")
    return redirect(request.META.get("HTTP_REFERER") or exam.course.get_absolute_url())
