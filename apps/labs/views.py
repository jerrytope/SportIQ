import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from . import engines
from .models import Run, Scenario


def _complete_lessons(user, scenario):
    from apps.learning import services as learning
    from apps.learning.models import Enrolment

    for lesson in scenario.lessons.select_related("module__course"):
        e = Enrolment.objects.filter(user=user, course=lesson.module.course).first()
        if e:
            learning.complete_lesson(e, lesson)


@login_required
def index(request):
    kind = request.GET.get("kind")
    qs = Scenario.objects.filter(is_published=True)
    if kind:
        qs = qs.filter(kind=kind)
    best = {}
    for r in request.user.lab_runs.filter(completed=True):
        best[r.scenario_id] = max(best.get(r.scenario_id, 0), r.score or 0)
    return render(request, "labs/index.html", {"scenarios": qs, "kinds": Scenario.KINDS, "kind": kind, "best": best})


@login_required
def play(request, slug):
    s = get_object_or_404(Scenario, slug=slug, is_published=True)
    if s.requires_qualified and not (request.user.is_verified_professional or request.user.is_backoffice):
        return render(request, "labs/restricted.html", {"s": s}, status=403)
    run = Run.objects.filter(scenario=s, user=request.user, completed=False).first()
    if request.GET.get("restart") and run:
        run.delete()
        run = None
    if request.method == "POST":
        run = run or Run.objects.create(scenario=s, user=request.user)
        if s.engine == "branching":
            try:
                opt = engines.branching_step(s, run, int(request.POST.get("option")))
            except (TypeError, ValueError):
                opt = None
            if opt is None:
                messages.error(request, "Choose an option.")
        elif s.engine == "annotate":
            try:
                ann = json.loads(request.POST.get("annotations", "[]"))[:100]
            except ValueError:
                ann = []
            run.path, run.report = ann, request.POST.get("report", "")[:10000]
            run.score, run.feedback = engines.score_annotate(s, ann, run.report)
            run.completed = True
        elif s.engine == "load":
            flagged = request.POST.getlist("flag")
            run.score, run.feedback, rows = engines.score_load(s, flagged)
            run.path, run.completed = rows, True
        elif s.engine == "designer":
            ids = [i for i in request.POST.get("order", "").split(",") if i]
            run.path = ids
            run.score, run.feedback = engines.score_designer(s, ids)
            run.completed = True
        elif s.engine == "budget":
            alloc = {}
            for line in s.data.get("lines", []):
                try:
                    alloc[line["key"]] = max(0, int(float(request.POST.get(line["key"], 0) or 0)))
                except ValueError:
                    alloc[line["key"]] = 0
            run.path = alloc
            run.score, run.feedback = engines.score_budget(s, alloc)
            run.completed = True
        run.save()
        if run.completed:
            _complete_lessons(request.user, s)
            return redirect("labs:result", pk=run.pk)
        return redirect("labs:play", slug=slug)
    ctx = {"s": s, "run": run}
    if s.engine == "branching":
        ctx["node_id"], ctx["node"] = engines.branching_current(s, run or Run(path=[]))
        ctx["history"] = run.path if run else []
    elif s.engine == "load":
        ctx["athletes"] = [{**a, "peak": max(a["weeks"]) or 1} for a in s.data.get("athletes", [])]
    return render(request, f"labs/play_{s.engine}.html", ctx)


@login_required
def result(request, pk):
    run = get_object_or_404(Run.objects.select_related("scenario"), pk=pk)
    if run.user != request.user and not request.user.has_role("instructor"):
        raise Http404
    return render(request, "labs/result.html", {"run": run, "s": run.scenario,
                                                "previous": run.scenario.runs.filter(user=run.user, completed=True).exclude(pk=run.pk)[:5]})
