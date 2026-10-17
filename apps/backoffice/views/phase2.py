"""Back office for Phases 2-4: generic records, approval queues, AI copilot, integrations, observatory."""
import io
import json
import zipfile

from django import forms
from django.contrib import messages
from django.core.management import call_command
from django.db.models import Avg, Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.ai import services as ai
from apps.ai.models import Message, RiskAlert
from apps.assessments.models import Appeal, Attempt, ExamExtension
from apps.catalog.models import Course
from apps.community.models import ContentReport, MentorProfile, Opportunity
from apps.core.audit import audit
from apps.credentials import services as cred_services
from apps.credentials.models import (CPDActivity, Credential, CredentialType, ExternalQualification, PriorLearningClaim,
                                     ProgrammeApplication, RenewalRequest)
from apps.integrations.models import SCOPES, ApiKey, ScormPackage, WebhookDelivery
from apps.integrations.scorm import extract
from apps.learning import services as learning
from apps.live.models import LiveSession, Registration
from apps.notifications.services import notify
from apps.practicals import services as practicals
from apps.practicals.models import Submission
from apps.research.models import DatasetRequest, PeerReview, Project, Publication

from ..decorators import staff_required
from ..resources import RESOURCES


def _resource(key, user):
    if key not in RESOURCES:
        raise Http404
    model, fields, label, roles, columns, help_text = RESOURCES[key]
    if not user.has_role(*roles):
        return None
    return model, fields, label, columns, help_text


def _form_for(model, fields):
    widgets = {}
    for f in fields:
        field = model._meta.get_field(f)
        t = field.get_internal_type()
        if t == "DateTimeField":
            widgets[f] = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
        elif t == "DateField":
            widgets[f] = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
        elif t in ("TextField",):
            widgets[f] = forms.Textarea(attrs={"rows": 4})
        elif t == "JSONField":
            widgets[f] = forms.Textarea(attrs={"rows": 8, "style": "font-family:ui-monospace,Consolas,monospace;font-size:.85rem"})
        elif t == "ManyToManyField":
            widgets[f] = forms.SelectMultiple(attrs={"size": 6})
    return forms.modelform_factory(model, fields=fields, widgets=widgets)


@staff_required()
def records(request, key):
    res = _resource(key, request.user)
    if not res:
        return render(request, "manage/forbidden.html", status=403)
    model, fields, label, columns, help_text = res
    rows = [{"obj": o, "cells": [getattr(o, f"get_{c}_display")() if hasattr(o, f"get_{c}_display") else getattr(o, c) for c in columns]}
            for o in model.objects.all()[:300]]
    return render(request, "manage/records/list.html", {"key": key, "label": label, "rows": rows,
                                                        "columns": [model._meta.get_field(c).verbose_name for c in columns], "help": help_text})


@staff_required()
def record_edit(request, key, pk=None):
    res = _resource(key, request.user)
    if not res:
        return render(request, "manage/forbidden.html", status=403)
    model, fields, label, _, help_text = res
    obj = get_object_or_404(model, pk=pk) if pk else None
    if request.method == "POST" and request.POST.get("action") == "delete" and obj:
        audit(request.user, f"{key}.deleted", obj, request=request)
        obj.delete()
        messages.success(request, "Deleted.")
        return redirect("backoffice:records", key=key)
    form = _form_for(model, fields)(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        audit(request.user, f"{key}.saved", item, {"fields": form.changed_data}, request)
        messages.success(request, "Saved.")
        return redirect("backoffice:records", key=key)
    extra = {}
    if key == "live-sessions" and obj and obj.kind == "in_person":
        extra["registrations"] = obj.registrations.select_related("user")
    return render(request, "manage/records/edit.html", {"form": form, "obj": obj, "key": key, "label": label, "help": help_text, **extra})


@staff_required("academic_manager", "instructor")
def mark_attendance(request, pk):
    s = get_object_or_404(LiveSession, pk=pk)
    present = set(int(x) for x in request.POST.getlist("present"))
    from apps.credentials.services import record_cpd

    for reg in s.registrations.select_related("user"):
        was = reg.attended
        reg.attended = reg.user_id in present
        if reg.attended and not reg.joined_at:
            reg.joined_at = timezone.now()
        reg.save()
        if reg.attended and not was:
            record_cpd(reg.user, f"In person: {s.title}", "practice", s.cpd_points, f"live:{s.pk}")
    messages.success(request, "Attendance saved.")
    return redirect("backoffice:record_edit", key="live-sessions", pk=pk)


# --- Practicals marking ---------------------------------------------------------------------------

@staff_required("instructor", "academic_manager")
def practicals_queue(request):
    qs = Submission.objects.select_related("task__course", "user")
    if not request.user.has_role("academic_manager"):
        qs = qs.filter(Q(task__course__instructors=request.user) | Q(task__course__owner=request.user)).distinct()
    return render(request, "manage/practicals/queue.html", {
        "pending": qs.filter(status="submitted"), "awaiting_supervisor": qs.filter(status="passed", task__requires_supervisor=True, supervisor_signed_at__isnull=True),
        "recent": qs.exclude(status="submitted")[:20],
    })


@staff_required("instructor", "academic_manager")
def practical_assess(request, pk):
    sub = get_object_or_404(Submission.objects.select_related("task__course", "user"), pk=pk)
    if request.method == "POST":
        if request.POST.get("action") == "ai_feedback":
            sub.ai_feedback = ai.preliminary_feedback(sub.task.rubric, sub.task.instructions, sub.text)
            sub.save(update_fields=["ai_feedback"])
            messages.info(request, "Draft feedback added below. Check it before using any of it.")
            return redirect("backoffice:practical_assess", pk=pk)
        scores = {str(i): request.POST.get(f"c{i}", 0) for i in range(len(sub.task.rubric))}
        practicals.assess(sub, scores, request.POST.get("feedback", ""), request.user,
                          outcome="revise" if request.POST.get("action") == "revise" else None)
        messages.success(request, f"Saved: {sub.get_status_display()}.")
        return redirect("backoffice:practicals")
    criteria = [{"i": i, "title": c.get("title"), "max": c.get("max"), "score": sub.rubric_scores.get(str(i), "")} for i, c in enumerate(sub.task.rubric)]
    return render(request, "manage/practicals/assess.html", {"sub": sub, "criteria": criteria,
                                                             "history": sub.task.submissions.filter(user=sub.user).exclude(pk=sub.pk)})


# --- Appeals & resits ------------------------------------------------------------------------------

@staff_required("instructor", "academic_manager")
def appeals(request):
    if request.method == "POST":
        a = get_object_or_404(Appeal, pk=request.POST.get("appeal"), status="open")
        decision = request.POST.get("decision")
        a.outcome = request.POST.get("outcome", "")[:2000]
        a.decided_by = request.user
        if decision == "uphold":
            a.status = "upheld"
            if a.kind in ("resit", "result", "access"):
                ExamExtension.objects.create(exam=a.exam, user=a.user, extra_attempts=1, reason=f"Appeal #{a.pk}: {a.get_kind_display()}",
                                             granted_by=request.user)
            if a.kind == "result" and a.attempt and a.attempt.status == Attempt.RELEASED:
                a.attempt.status = Attempt.SUBMITTED  # reopen for re-marking
                a.attempt.save(update_fields=["status"])
        else:
            a.status = "dismissed"
        a.save()
        audit(request.user, f"appeal.{a.status}", a, {"outcome": a.outcome}, request)
        notify(a.user, f"Your {a.get_kind_display().lower()}: {a.get_status_display().lower()}", a.outcome, f"/learn/attempts/{a.attempt_id}/" if a.attempt_id else "/learn/")
        messages.success(request, "Decision recorded.")
        return redirect("backoffice:appeals")
    return render(request, "manage/assessments/appeals.html", {"open": Appeal.objects.filter(status="open").select_related("user", "exam", "attempt"),
                                                               "closed": Appeal.objects.exclude(status="open").select_related("user", "exam")[:20]})


@staff_required("instructor", "academic_manager")
def moderate(request, pk):
    att = get_object_or_404(Attempt, pk=pk, status=Attempt.MARKED)
    if any(r.marked_by_id == request.user.pk for r in att.responses.all()):
        messages.error(request, "Moderation must be done by a different examiner from the first marker.")
    else:
        att.moderated_by = request.user
        att.moderation_note = request.POST.get("note", "")[:2000]
        att.save(update_fields=["moderated_by", "moderation_note"])
        audit(request.user, "exam.moderated", att, {"note": att.moderation_note}, request)
        messages.success(request, "Moderated. The result can now be released.")
    return redirect("backoffice:mark_attempt", pk=pk)


# --- Registrar queues ---------------------------------------------------------------------------------

@staff_required("registrar")
def registrar(request):
    if request.method == "POST":
        kind, pk, decision = request.POST.get("kind"), request.POST.get("id"), request.POST.get("decision")
        note = request.POST.get("note", "")[:255]
        if kind == "cpd":
            a = get_object_or_404(CPDActivity, pk=pk, status="pending")
            a.status = "approved" if decision == "approve" else "rejected"
            a.points = a.hours if decision == "approve" else 0
            if request.POST.get("points"):
                a.points = request.POST["points"]
            a.reviewed_by, a.review_note = request.user, note
            a.save()
            notify(a.user, f"CPD {a.get_status_display().lower()}: {a.title}", note, "/credentials/cpd/")
        elif kind == "renewal":
            r = get_object_or_404(RenewalRequest, pk=pk, status="pending")
            r.status, r.decided_by = ("approved" if decision == "approve" else "rejected"), request.user
            r.save()
            if r.status == "approved":
                cred_services.renew(r.credential, request.user, note)
            else:
                notify(r.credential.user, f"Renewal not approved: {r.credential.title}", note, "/credentials/cpd/")
        elif kind == "rpl":
            c = get_object_or_404(PriorLearningClaim, pk=pk, status="submitted")
            c.status, c.decision_note, c.decided_by = ("approved" if decision == "approve" else "rejected"), note, request.user
            c.save()
            if c.status == "approved":
                enr, _ = learning.enrol(c.user, c.course, source="admin")
                enr.status, enr.progress, enr.completed_at = "completed", 100, timezone.now()
                enr.save()
                rpl_type, _ = CredentialType.objects.get_or_create(code="rpl", defaults={"name": "Recognition of Prior Learning", "kind": "completion"})
                cred_services.issue(c.user, rpl_type, f"{c.course.title} (recognised prior learning)", course=c.course, actor=request.user)
                cred_services.check_programmes(c.user)
            notify(c.user, f"Prior learning claim {c.get_status_display().lower()}", note, c.course.get_absolute_url())
        elif kind == "external":
            q = get_object_or_404(ExternalQualification, pk=pk, status="submitted")
            q.status, q.note, q.verified_by = ("verified" if decision == "approve" else "rejected"), note, request.user
            q.save()
            notify(q.user, f"External qualification {q.get_status_display().lower()}: {q.title}", note, "/credentials/external/")
        elif kind == "programme_app":
            a = get_object_or_404(ProgrammeApplication, pk=pk, status="submitted")
            a.status, a.decision_note = ("admitted" if decision == "approve" else "rejected"), note
            a.save()
            notify(a.user, f"Programme application: {a.get_status_display().lower()}", note, a.programme.get_absolute_url())
        audit(request.user, f"registrar.{kind}.{decision}", None, {"id": pk, "note": note}, request)
        messages.success(request, "Decision saved.")
        return redirect(f"{request.path}#{kind}")
    return render(request, "manage/registrar.html", {
        "cpd": CPDActivity.objects.filter(status="pending").select_related("user"),
        "renewals": RenewalRequest.objects.filter(status="pending").select_related("credential__user", "credential__credential_type"),
        "rpl": PriorLearningClaim.objects.filter(status="submitted").select_related("user", "course"),
        "external": ExternalQualification.objects.filter(status="submitted").select_related("user"),
        "programme_apps": ProgrammeApplication.objects.filter(status="submitted").select_related("user", "programme"),
    })


# --- Community moderation ------------------------------------------------------------------------------

@staff_required("community_moderator")
def moderation(request):
    if request.method == "POST":
        kind = request.POST.get("kind")
        if kind == "report":
            rep = get_object_or_404(ContentReport, pk=request.POST.get("id"))
            if request.POST.get("decision") == "remove" and rep.target is not None:
                target = rep.target
                if hasattr(target, "is_hidden"):
                    target.is_hidden = True
                    target.save(update_fields=["is_hidden"])
                elif hasattr(target, "status"):
                    target.status = "closed"
                    target.save(update_fields=["status"])
                rep.status = "actioned"
            else:
                rep.status = "dismissed"
            rep.handled_by, rep.action_note = request.user, request.POST.get("note", "")[:255]
            rep.save()
        elif kind == "opportunity":
            o = get_object_or_404(Opportunity, pk=request.POST.get("id"))
            o.status = "open" if request.POST.get("decision") == "approve" else "rejected"
            o.save(update_fields=["status"])
            if o.posted_by:
                notify(o.posted_by, f"Opportunity {o.get_status_display().lower()}: {o.title}", "", o.get_absolute_url())
        elif kind == "mentor":
            m = get_object_or_404(MentorProfile, pk=request.POST.get("id"))
            m.approved = request.POST.get("decision") == "approve"
            m.save(update_fields=["approved"])
            notify(m.user, "Mentor profile " + ("approved" if m.approved else "not approved"), "", "/community/mentors/")
        audit(request.user, f"moderation.{kind}", None, {"id": request.POST.get("id"), "decision": request.POST.get("decision")}, request)
        return redirect("backoffice:moderation")
    return render(request, "manage/moderation.html", {
        "reports": ContentReport.objects.filter(status="open").select_related("reporter", "content_type"),
        "opportunities": Opportunity.objects.filter(status="pending"), "mentors": MentorProfile.objects.filter(approved=False).select_related("user"),
    })


# --- Research office -----------------------------------------------------------------------------------

@staff_required("research_officer")
def research_office(request):
    from apps.accounts.models import User

    if request.method == "POST":
        kind, pk, decision = request.POST.get("kind"), request.POST.get("id"), request.POST.get("decision")
        if kind == "project":
            p = get_object_or_404(Project, pk=pk)
            p.status = "active" if decision == "approve" else "rejected"
            p.ethics_reference = request.POST.get("reference", "")[:100] or p.ethics_reference
            p.save()
            notify(p.lead, f"Research proposal {p.get_status_display().lower()}: {p.title}", request.POST.get("note", ""), p.get_absolute_url())
        elif kind == "dataset":
            r = get_object_or_404(DatasetRequest, pk=pk)
            r.status, r.decided_by = ("approved" if decision == "approve" else "rejected"), request.user
            r.expires_on = timezone.localdate() + timezone.timedelta(days=365) if r.status == "approved" else None
            r.save()
            notify(r.user, f"Dataset request {r.get_status_display().lower()}: {r.dataset.title}", "", "/research/")
        elif kind == "reviewer":
            pub = get_object_or_404(Publication, pk=pk)
            rev = User.objects.filter(email__iexact=request.POST.get("email", "").strip()).first()
            if rev and rev != pub.submitted_by:
                PeerReview.objects.get_or_create(publication=pub, reviewer=rev)
                notify(rev, "You've been invited to peer review", pub.title, "/research/")
            else:
                messages.error(request, "Reviewer must have a SportIQ account and can't be the author.")
        elif kind == "publish":
            pub = get_object_or_404(Publication, pk=pk)
            pub.status = {"publish": "published", "revise": "revise", "reject": "rejected"}.get(decision, pub.status)
            if pub.status == "published":
                pub.published_on = timezone.localdate()
            pub.save()
            notify(pub.submitted_by, f"Publication {pub.get_status_display().lower()}: {pub.title}", "", f"/research/publications/{pub.pk}/")
        audit(request.user, f"research.{kind}.{decision}", None, {"id": pk}, request)
        return redirect("backoffice:research_office")
    return render(request, "manage/research.html", {
        "proposals": Project.objects.filter(status__in=["proposal", "ethics"]).select_related("lead"),
        "dataset_requests": DatasetRequest.objects.filter(status="pending").select_related("user", "dataset"),
        "in_review": Publication.objects.filter(status__in=["review", "revise"]).prefetch_related("reviews__reviewer"),
    })


# --- Content studio extras: SCORM upload, AI copilot ----------------------------------------------------

@staff_required("course_creator", "academic_manager")
def scorm_upload(request, lesson_id):
    from apps.catalog.models import Lesson

    lesson = get_object_or_404(Lesson, pk=lesson_id)
    if request.method == "POST" and request.FILES.get("package"):
        pkg, _ = ScormPackage.objects.update_or_create(lesson=lesson, defaults={"package": request.FILES["package"]})
        try:
            extract(pkg)
            lesson.kind = "scorm"
            lesson.save(update_fields=["kind"])
            messages.success(request, f"SCORM {pkg.version} package installed (launch: {pkg.launch_path}).")
        except Exception as exc:  # noqa: BLE001 - show the reason (bad zip, missing manifest)
            pkg.delete()
            messages.error(request, f"Couldn't install package: {exc}")
    return redirect("backoffice:lesson_edit", pk=lesson_id)


@staff_required("course_creator", "academic_manager", "instructor")
def copilot(request, pk):
    course = get_object_or_404(Course, pk=pk)
    drafts = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "questions":
            text = " ".join(l.body + " " + l.transcript for l in course.lessons().filter(pk__in=request.POST.getlist("lessons")) or course.lessons())
            drafts = ai.draft_questions(course, text, n=int(request.POST.get("n", 5) or 5))
            messages.success(request, f"{len(drafts)} draft question(s) added to the question bank as inactive drafts for expert review.")
        elif action == "objectives":
            course.objectives = ai.draft_objectives(course)
            course.save(update_fields=["objectives"])
            messages.success(request, "Draft objectives written to course settings. Review them before submitting.")
        elif action == "approve":
            from apps.assessments.models import Question

            n = Question.objects.filter(bank__course=course, ai_draft=True, pk__in=request.POST.getlist("q")).update(ai_draft=False, is_active=True,
                                                                                                                        is_practice=request.POST.get("as_practice") == "on")
            messages.success(request, f"{n} question(s) approved.")
        return redirect("backoffice:copilot", pk=pk)
    from apps.assessments.models import Question

    return render(request, "manage/studio/copilot.html", {"course": course, "lessons": course.lessons(),
                                                          "drafts": Question.objects.filter(bank__course=course, ai_draft=True).prefetch_related("choices")})


@staff_required("academic_manager", "instructor", "analyst")
def ai_centre(request):
    if request.method == "POST":
        if request.POST.get("action") == "reindex" and request.user.has_role("academic_manager"):
            n = ai.rebuild_index()
            messages.success(request, f"AI index rebuilt from approved content: {n} passages.")
        elif request.POST.get("action") == "scan":
            messages.success(request, f"{ai.scan_risks()} new learning-risk alert(s).")
        elif request.POST.get("resolve"):
            RiskAlert.objects.filter(pk=request.POST["resolve"]).update(resolved=True, resolved_by=request.user)
        return redirect("backoffice:ai_centre")
    from django.conf import settings

    from apps.ai.models import Chunk

    msgs = Message.objects.filter(role="assistant")
    alerts = RiskAlert.objects.filter(resolved=False).select_related("enrolment__user", "enrolment__course")
    if not request.user.has_role("academic_manager"):
        alerts = alerts.filter(Q(enrolment__course__instructors=request.user) | Q(enrolment__course__owner=request.user)).distinct()
    return render(request, "manage/ai.html", {
        "chunks": Chunk.objects.count(), "live": ai.ai_enabled(), "model": ai.ai_model(), "provider": {"openai": "OpenAI", "anthropic": "Anthropic"}.get(settings.AI_PROVIDER, ""),
        "answers": msgs.count(), "refused": msgs.filter(refused=True).count(),
        "helpful": msgs.filter(helpful=True).count(), "unhelpful": msgs.filter(helpful=False).count(),
        "alerts": alerts[:100],
        "low_rated": msgs.filter(helpful=False).select_related("conversation")[:10],
    })


# --- Integrations ------------------------------------------------------------------------------------------

@staff_required("super_admin")
def integrations(request):
    from apps.institutions.models import Institution

    new_key = None
    if request.method == "POST":
        if request.POST.get("action") == "create_key":
            scopes = [s for s in request.POST.getlist("scopes") if s in dict(SCOPES)]
            inst = Institution.objects.filter(pk=request.POST.get("institution")).first()
            key, new_key = ApiKey.generate(name=request.POST.get("name", "API key")[:120], scopes=scopes, institution=inst, created_by=request.user)
            audit(request.user, "api_key.created", key, {"scopes": scopes}, request)
        elif request.POST.get("action") == "revoke":
            ApiKey.objects.filter(pk=request.POST.get("key")).update(is_active=False)
            audit(request.user, "api_key.revoked", None, {"key": request.POST.get("key")}, request)
        if not new_key:
            return redirect("backoffice:integrations")
    return render(request, "manage/integrations.html", {
        "keys": ApiKey.objects.select_related("institution"), "new_key": new_key, "scopes": SCOPES,
        "institutions": Institution.objects.filter(is_active=True), "deliveries": WebhookDelivery.objects.select_related("webhook")[:15],
    })


@staff_required("super_admin")
def data_export(request):
    """Full data export for migration / exit (blueprint Module 19: avoid vendor lock-in). Integrity cases excluded."""
    buf = io.BytesIO()
    apps = ["accounts", "institutions", "catalog", "learning", "assessments", "credentials", "commerce", "support", "live",
            "library", "practicals", "careers", "community", "workforce", "research", "web"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for label in apps:
            out = io.StringIO()
            call_command("dumpdata", label, format="json", indent=1, stdout=out)
            z.writestr(f"{label}.json", out.getvalue())
        z.writestr("README.txt", "SportIQ data export. Load into a fresh SportIQ install with `python manage.py loaddata <file>.json` "
                                 "in dependency order (accounts, institutions, catalog, ...). Media files are exported separately "
                                 "from the storage bucket. Confidential integrity cases are exported only by safeguarding officers.")
    audit(request.user, "system.data_exported", None, {"apps": apps}, request)
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="sportiq-export-{timezone.localdate()}.zip"'
    return resp


# --- Observatory & impact ----------------------------------------------------------------------------------

@staff_required("analyst", "academic_manager")
def impact(request):
    from apps.analytics.services import impact_summary

    return render(request, "manage/impact.html", impact_summary())
