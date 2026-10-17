from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Course
from apps.support.models import Ticket, TicketMessage

from . import services
from .models import Conversation, Message, StudyPlan

DAILY_LIMIT = 80


def _rate_ok(user):
    key = f"ai-count:{user.pk}"
    n = cache.get(key, 0)
    cache.set(key, n + 1, 60 * 60 * 24)
    return n < DAILY_LIMIT


@login_required
def assistant(request, pk=None):
    convs = request.user.ai_conversations.filter(mode="tutor")[:20]
    conv = get_object_or_404(Conversation, pk=pk, user=request.user) if pk else None
    return render(request, "ai/assistant.html", {
        "convs": convs, "conv": conv, "msgs": conv.messages.all() if conv else [],
        "courses": Course.objects.filter(enrolments__user=request.user).distinct(),
        "blocked": services.open_attempt(request.user), "ai_live": services.ai_enabled(),
        "suggestions": ["What is strict liability in anti-doping?", "How should I respond if a child discloses abuse?",
                        "How do I structure a 60-minute training session?", "What is progressive overload?"],
    })


@login_required
@require_POST
def ask(request):
    question = request.POST.get("q", "").strip()[:2000]
    mode = request.POST.get("mode", "tutor") if request.POST.get("mode") in ("tutor", "support") else "tutor"
    conv = Conversation.objects.filter(pk=request.POST.get("conversation"), user=request.user).first()
    if not question:
        return redirect(conv and f"/ai/c/{conv.pk}/" or "ai:assistant")
    if not _rate_ok(request.user):
        messages.error(request, "You've reached today's limit for the assistant. It resets tomorrow.")
        return redirect("ai:assistant")
    course = Course.objects.filter(pk=request.POST.get("course")).first()
    if not conv:
        conv = Conversation.objects.create(user=request.user, mode=mode, title=question[:120], course=course)
    history = [{"role": m.role, "content": m.content} for m in conv.messages.all()]
    Message.objects.create(conversation=conv, role="user", content=question)
    result = services.answer(request.user, question, history, course=conv.course or course, mode=mode)
    Message.objects.create(conversation=conv, role="assistant", content=result["content"], citations=result["citations"],
                           engine=result["engine"], refused=result["refused"])
    conv.save()
    if mode == "support":
        return redirect("ai:support_chat", pk=conv.pk)
    return redirect("ai:conversation", pk=conv.pk)


@login_required
@require_POST
def rate(request, msg_id):
    m = get_object_or_404(Message, pk=msg_id, conversation__user=request.user, role="assistant")
    m.helpful = request.POST.get("helpful") == "yes"
    m.save(update_fields=["helpful"])
    return redirect(request.META.get("HTTP_REFERER") or "ai:assistant")


@login_required
def study_plan(request):
    plan = request.user.study_plans.filter(is_active=True).first()
    if request.method == "POST":
        goal = request.POST.get("goal", "").strip()[:255] or "Keep my qualifications current"
        try:
            hours = max(1, min(20, int(request.POST.get("hours", 3))))
        except ValueError:
            hours = 3
        weeks, narrative = services.build_study_plan(request.user, goal, hours)
        request.user.study_plans.update(is_active=False)
        StudyPlan.objects.create(user=request.user, goal=goal, hours_per_week=hours, weeks=weeks, narrative=narrative)
        messages.success(request, "Your study plan is ready.")
        return redirect("ai:study_plan")
    return render(request, "ai/study_plan.html", {"plan": plan})


@login_required
def revise(request):
    course = Course.objects.filter(slug=request.GET.get("course"), enrolments__user=request.user).first()
    practice = services.practice_questions(request.user, course) if course else []
    result = None
    if request.method == "POST" and course:
        from apps.assessments.models import Question

        result = []
        for q in Question.objects.filter(pk__in=request.POST.getlist("qid"), is_practice=True).prefetch_related("choices"):
            chosen = set(int(x) for x in request.POST.getlist(f"q{q.pk}") if x.isdigit())
            correct = set(c.pk for c in q.choices.all() if c.is_correct)
            result.append({"q": q, "ok": chosen == correct, "chosen": chosen})
        practice = []
    return render(request, "ai/revise.html", {
        "weak": services.revision_for(request.user), "courses": Course.objects.filter(enrolments__user=request.user).distinct(),
        "course": course, "practice": practice, "result": result,
        "score": sum(r["ok"] for r in result) if result else None,
    })


@login_required
def support_chat(request, pk=None):
    conv = get_object_or_404(Conversation, pk=pk, user=request.user, mode="support") if pk else None
    if request.method == "POST" and conv and request.POST.get("action") == "escalate" and not conv.escalated_ticket:
        transcript = "\n\n".join(f"{m.role.upper()}: {m.content}" for m in conv.messages.all())
        t = Ticket.objects.create(user=request.user, category=request.POST.get("category", "technical"), subject=conv.title[:200])
        TicketMessage.objects.create(ticket=t, author=request.user, body=f"(Escalated from the help assistant)\n\n{transcript}")
        conv.escalated_ticket = t
        conv.save()
        messages.success(request, f"Passed to our support team as ticket {t.reference}.")
        return redirect("support:ticket", pk=t.pk)
    return render(request, "ai/support.html", {"conv": conv, "msgs": conv.messages.all() if conv else [], "categories": Ticket.CATEGORIES})
