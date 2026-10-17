import csv
from datetime import date, timedelta

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import NIGERIAN_STATES, DataRequest
from apps.analytics import services as metrics
from apps.analytics.models import MetricDefinition
from apps.assessments.models import Attempt
from apps.catalog.models import Course, Profession
from apps.core.audit import audit
from apps.institutions.models import institutions_admined_by
from apps.learning.models import Application
from apps.support.models import Ticket
from apps.web.models import DemoRequest

from ..decorators import staff_required


@staff_required()
def home(request):
    user = request.user
    if not user.staff_roles and not user.is_superuser:
        orgs = institutions_admined_by(user)
        if orgs.exists():
            return redirect("backoffice:org", slug=orgs.first().slug)
    today = timezone.localdate()
    kpis = metrics.compute(today - timedelta(days=30), today)
    tasks = []
    if user.has_role("reviewer", "academic_manager"):
        n = Course.objects.filter(status=Course.IN_REVIEW).count()
        tasks.append(("Courses awaiting review", n, "backoffice:review_queue", "clipboard"))
    if user.has_role("instructor", "academic_manager"):
        n = Attempt.objects.filter(status__in=[Attempt.SUBMITTED, Attempt.MARKED]).count()
        tasks.append(("Exam attempts to mark or release", n, "backoffice:marking", "check-circle"))
    if user.has_role("academic_manager"):
        n = Application.objects.filter(status__in=["submitted", "review"]).count()
        tasks.append(("Admission applications", n, "backoffice:admissions", "file"))
    if user.has_role("support_agent"):
        n = Ticket.objects.filter(status="open").count()
        tasks.append(("Open support tickets", n, "backoffice:tickets", "headphones"))
    if user.has_role("comms_officer"):
        tasks.append(("New demo requests", DemoRequest.objects.filter(status="new").count(), "backoffice:site", "megaphone"))
    if user.has_role("super_admin"):
        tasks.append(("Open data-subject requests", DataRequest.objects.filter(status="open").count(),
                      "backoffice:data_requests", "lock"))
    if user.has_role("course_creator"):
        mine = Course.objects.filter(owner=user).exclude(status=Course.RETIRED).count()
        tasks.append(("My courses in the studio", mine, "backoffice:studio", "edit"))
    return render(request, "manage/home.html", {
        "kpis": kpis, "tasks": tasks, "monthly": metrics.monthly_registrations(),
        "overdue_tickets": Ticket.objects.filter(status="open", sla_due__lt=timezone.now()).count()
        if user.has_role("support_agent") else None,
    })


def _filters(request):
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get("start", ""))
    except ValueError:
        start = today - timedelta(days=90)
    try:
        end = date.fromisoformat(request.GET.get("end", ""))
    except ValueError:
        end = today
    return start, end, request.GET.get("state") or None, request.GET.get("profession") or None


@staff_required("analyst", "academic_manager")
def analytics(request):
    metrics.ensure_definitions()
    start, end, state, profession = _filters(request)
    data = metrics.compute(start, end, state, profession)
    by_state = metrics.breakdown_by_state(state, profession)
    peak_state = max((r["n"] for r in by_state), default=1) or 1
    by_prof = metrics.breakdown_by_profession(state)
    peak_prof = max((r["n"] for r in by_prof), default=1) or 1
    return render(request, "manage/analytics.html", {
        "data": data, "start": start, "end": end, "state": state, "profession": profession,
        "states": NIGERIAN_STATES, "professions": Profession.objects.all(),
        "definitions": {d.code: d for d in MetricDefinition.objects.all()},
        "by_state": by_state, "peak_state": peak_state, "by_prof": by_prof, "peak_prof": peak_prof,
        "courses": metrics.course_table(), "monthly": metrics.monthly_registrations(state=state, profession=profession),
    })


@staff_required("analyst", "academic_manager")
def analytics_export(request):
    start, end, state, profession = _filters(request)
    data = metrics.compute(start, end, state, profession)
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="sportiq-report-{start}-{end}.csv"'
    w = csv.writer(resp)
    w.writerow(["SportIQ report", f"{start} to {end}", f"state={state or 'all'}", f"profession={profession or 'all'}"])
    w.writerow([])
    w.writerow(["Metric", "Value", "Definition"])
    defs = {c: (n, d) for c, n, d, _ in metrics.DEFINITIONS}
    for code, value in data.items():
        name, definition = defs.get(code, (code, ""))
        w.writerow([name, value, definition])
    w.writerow([])
    w.writerow(["Course", "Enrolled", "Completed", "Completion %", "Rating"])
    for r in metrics.course_table():
        w.writerow([r["course"].title, r["enrolled"], r["completed"], r["rate"], r["rating"] or ""])
    w.writerow([])
    w.writerow(["State", "Learners", "Completions"])
    for r in metrics.breakdown_by_state(state, profession):
        w.writerow([r["state"], r["n"], r["done"]])
    audit(request.user, "report.exported", None, {"start": str(start), "end": str(end)}, request)
    return resp
