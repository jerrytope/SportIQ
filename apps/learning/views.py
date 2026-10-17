from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language
from django.views.decorators.http import require_POST

from apps.catalog.models import Course, Lesson
from apps.credentials.models import Credential, MandatoryRequirement
from apps.live.models import LiveSession
from apps.notifications.services import announcements_for, notify

from . import services
from .models import (Application, Badge, Bookmark, CourseFeedback, Enrolment, LessonProgress, Note, Post, Thread,
                     UserBadge)


def _enrolment_or_404(user, slug):
    return get_object_or_404(Enrolment.objects.select_related("course"), user=user, course__slug=slug,
                             status__in=["active", "completed"])


@login_required
def dashboard(request):
    user = request.user
    active = list(user.enrolments.filter(status="active").select_related("course", "course__track", "last_lesson"))
    current = active[0] if active else None
    soon = timezone.now() + timedelta(days=60)
    renewals = user.credentials.filter(status="active", expires_at__isnull=False, expires_at__lte=soon)
    # Mandatory learning for the user's professions that they haven't completed
    done_ids = set(user.enrolments.filter(status="completed").values_list("course_id", flat=True))
    required = (MandatoryRequirement.objects.filter(profession__in=user.professions.all())
                .exclude(course_id__in=done_ids).select_related("course", "profession"))
    enrolled_ids = set(user.enrolments.values_list("course_id", flat=True))
    recommended = (Course.objects.published().filter(professions__in=user.professions.all())
                   .exclude(pk__in=enrolled_ids).distinct().select_related("track")[:3])
    if not recommended:
        recommended = Course.objects.published().exclude(pk__in=enrolled_ids).select_related("track")[:3]
    deadlines = [e for e in active if e.due_date]
    return render(request, "learning/dashboard.html", {
        "current": current, "next_lesson": services.next_lesson(current) if current else None,
        "active": active, "completed_count": user.enrolments.filter(status="completed").count(),
        "credential_count": user.credentials.filter(status="active").count(),
        "streak": services.streak(user), "renewals": renewals, "required": required,
        "recommended": recommended, "announcements": announcements_for(user)[:3], "deadlines": deadlines,
        "badges": user.badges.select_related("badge")[:4],
        "pending_nominations": user.nominations.filter(status="pending").select_related("course", "institution"),
        "surveys": [s for e in user.enrolments.filter(status="completed") for s in e.outcome_surveys.filter(responded_at__isnull=True)],
        "live_soon": LiveSession.objects.filter(registrations__user=user, starts_at__gte=timezone.now() - timedelta(hours=2))
        .order_by("starts_at")[:3],
        "study_plan": user.study_plans.filter(is_active=True).first(),
    })


@login_required
def my_learning(request):
    tab = request.GET.get("tab", "active")
    qs = request.user.enrolments.select_related("course", "course__track")
    qs = qs.filter(status="completed") if tab == "completed" else qs.filter(status="active")
    return render(request, "learning/my_learning.html", {
        "enrolments": qs, "tab": tab,
        "bookmarks": request.user.bookmarks.select_related("lesson__module__course")[:20] if tab == "saved" else None,
        "applications": request.user.applications.select_related("course") if tab == "applications" else None,
    })


@login_required
@require_POST
def enrol(request, slug):
    course = get_object_or_404(Course.objects.published(), slug=slug)
    if services.prerequisites_missing(request.user, course):
        messages.error(request, "Complete the prerequisite courses first.")
        return redirect(course)
    if not course.is_free:
        return redirect("commerce:checkout", slug=slug)
    if course.requires_application and not course.applications.filter(user=request.user, status="admitted").exists():
        return redirect("learning:apply", slug=slug)
    enrolment, created = services.enrol(request.user, course)
    if created:
        messages.success(request, f"You're enrolled in {course.title}. Let's begin!")
    return redirect("learning:course", slug=slug)


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["statement", "document"]
        labels = {"document": "Supporting document (CV, certificate or letter), optional"}
        widgets = {"statement": forms.Textarea(attrs={"rows": 6})}


@login_required
def apply(request, slug):
    course = get_object_or_404(Course.objects.published(), slug=slug, requires_application=True)
    if Application.objects.filter(user=request.user, course=course).exists():
        messages.info(request, "You have already applied for this programme.")
        return redirect(course)
    form = ApplicationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        app = form.save(commit=False)
        app.user, app.course = request.user, course
        app.save()
        notify(request.user, f"Application received: {course.title}",
               "We'll review your application and let you know the outcome.", course.get_absolute_url())
        messages.success(request, "Application submitted.")
        return redirect(course)
    return render(request, "learning/apply.html", {"course": course, "form": form})


@login_required
def course_home(request, slug):
    enrolment = _enrolment_or_404(request.user, slug)
    last = enrolment.last_lesson
    if last and enrolment.lesson_progress.filter(lesson=last, completed=True).exists():
        last = None  # finished it: move on to the next incomplete lesson
    lesson = last or services.next_lesson(enrolment) or enrolment.course.lessons().first()
    if not lesson:
        messages.info(request, "This course has no lessons yet.")
        return redirect(enrolment.course)
    return redirect("learning:lesson", slug=slug, pk=lesson.pk)


def _outline(course, enrolment):
    done = set()
    if enrolment:
        done = set(enrolment.lesson_progress.filter(completed=True).values_list("lesson_id", flat=True))
    return course.modules.prefetch_related("lessons"), done


@login_required
def lesson(request, slug, pk):
    enrolment = _enrolment_or_404(request.user, slug)
    course = enrolment.course
    lesson = get_object_or_404(Lesson.objects.select_related("module", "exam"), pk=pk, module__course=course)
    progress = services.touch(enrolment, lesson)
    lessons = list(course.lessons())
    idx = lessons.index(lesson)
    modules, done = _outline(course, enrolment)
    exam_state = None
    if lesson.exam_id:
        exam = lesson.exam
        attempts = exam.attempts_for(request.user)
        exam_state = {
            "exam": exam, "attempts": attempts, "used": attempts.count(), "allowed": exam.allowed_attempts(request.user),
            "open": exam.is_open_now(),
            "passed": attempts.filter(passed=True).exists(),
            "in_progress": exam.attempts.filter(user=request.user, status="in_progress").first(),
        }
    show_feedback = enrolment.status == "completed" and not hasattr(enrolment, "feedback")
    return render(request, "learning/lesson.html", {
        "enrolment": enrolment, "course": course, "lesson": lesson, "progress": progress,
        "prev": lessons[idx - 1] if idx > 0 else None, "next": lessons[idx + 1] if idx + 1 < len(lessons) else None,
        "modules": modules, "done": done, "position": idx + 1, "total": len(lessons),
        "notes": request.user.notes.filter(lesson=lesson),
        "bookmarked": Bookmark.objects.filter(user=request.user, lesson=lesson).exists(),
        "exam_state": exam_state, "show_feedback": show_feedback,
        "threads": course.threads.filter(is_hidden=False).annotate(n=Count("posts"))[:5],
        "credential": Credential.objects.filter(user=request.user, course=course).first(),
        "ltr": lesson.translations.filter(language=get_language(), status="approved").first()
        if get_language() and not get_language().startswith("en") else None,
    })


def preview(request, slug, pk):
    lesson = get_object_or_404(Lesson.objects.select_related("module__course"), pk=pk, module__course__slug=slug,
                               is_preview=True, module__course__status=Course.PUBLISHED)
    return render(request, "learning/preview.html", {"lesson": lesson, "course": lesson.module.course,
                                                     "base": "app/base.html" if request.user.is_authenticated else "public/base.html"})


@login_required
@require_POST
def save_position(request, slug, pk):
    enrolment = _enrolment_or_404(request.user, slug)
    lesson = get_object_or_404(Lesson, pk=pk, module__course=enrolment.course)
    try:
        position = max(0, int(request.POST.get("position", 0)))
    except ValueError:
        return HttpResponseBadRequest()
    services.touch(enrolment, lesson, position)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def complete(request, slug, pk):
    enrolment = _enrolment_or_404(request.user, slug)
    lesson = get_object_or_404(Lesson, pk=pk, module__course=enrolment.course)
    if lesson.kind == "quiz" and lesson.exam_id:
        if not lesson.exam.attempts.filter(user=request.user, passed=True, status="released").exists():
            messages.error(request, "Pass the assessment to complete this lesson.")
            return redirect("learning:lesson", slug=slug, pk=pk)
    services.complete_lesson(enrolment, lesson)
    enrolment.refresh_from_db()
    if enrolment.status == "completed":
        messages.success(request, f"Congratulations! You've completed {enrolment.course.title}.")
        return redirect("learning:lesson", slug=slug, pk=pk)
    nxt = services.next_lesson(enrolment)
    if nxt:
        return redirect("learning:lesson", slug=slug, pk=nxt.pk)
    exam = enrolment.course.final_exam()
    if exam and enrolment.course.completion_requires_exam:
        messages.info(request, "All lessons done. Pass the final assessment to complete the course.")
    return redirect("learning:lesson", slug=slug, pk=pk)


@login_required
@require_POST
def add_note(request, slug, pk):
    enrolment = _enrolment_or_404(request.user, slug)
    lesson = get_object_or_404(Lesson, pk=pk, module__course=enrolment.course)
    body = request.POST.get("body", "").strip()
    if body:
        at = request.POST.get("at_seconds")
        Note.objects.create(user=request.user, lesson=lesson, body=body[:5000],
                            at_seconds=int(at) if at and at.isdigit() and lesson.kind == "video" else None)
    return redirect(f"{lesson.get_absolute_url()}#notes")


@login_required
@require_POST
def delete_note(request, note_id):
    note = get_object_or_404(Note, pk=note_id, user=request.user)
    url = note.lesson.get_absolute_url()
    note.delete()
    return redirect(f"{url}#notes")


@login_required
@require_POST
def toggle_bookmark(request, slug, pk):
    enrolment = _enrolment_or_404(request.user, slug)
    lesson = get_object_or_404(Lesson, pk=pk, module__course=enrolment.course)
    bm, created = Bookmark.objects.get_or_create(user=request.user, lesson=lesson)
    if not created:
        bm.delete()
    return redirect(lesson.get_absolute_url())


class FeedbackForm(forms.ModelForm):
    RATING = [(i, f"{i} ★") for i in range(5, 0, -1)]
    course_rating = forms.TypedChoiceField(choices=RATING, coerce=int, widget=forms.RadioSelect, label="Overall, how was this course?")
    instructor_rating = forms.TypedChoiceField(choices=RATING, coerce=int, widget=forms.RadioSelect, required=False,
                                               empty_value=None, label="How clear was the teaching?")
    relevance_rating = forms.TypedChoiceField(choices=RATING, coerce=int, widget=forms.RadioSelect, required=False,
                                              empty_value=None, label="How relevant is it to your work?")

    class Meta:
        model = CourseFeedback
        fields = ["course_rating", "instructor_rating", "relevance_rating", "comment"]
        widgets = {"comment": forms.Textarea(attrs={"rows": 3})}
        labels = {"comment": "Anything we should improve?"}


@login_required
def feedback(request, slug):
    enrolment = _enrolment_or_404(request.user, slug)
    if hasattr(enrolment, "feedback"):
        messages.info(request, "Thanks, you've already given feedback for this course.")
        return redirect("learning:course", slug=slug)
    form = FeedbackForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        fb = form.save(commit=False)
        fb.enrolment = enrolment
        fb.save()
        messages.success(request, "Thank you for your feedback.")
        return redirect("learning:my_learning")
    return render(request, "learning/feedback.html", {"form": form, "course": enrolment.course})


# --- Discussions & moderated Q&A -----------------------------------------------------

class ThreadForm(forms.ModelForm):
    class Meta:
        model = Thread
        fields = ["title", "body", "is_question"]
        labels = {"is_question": "This is a question for the instructor", "body": "Details"}
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}


def _can_moderate(user, course):
    return user.has_role("instructor", "academic_manager") or course.instructors.filter(pk=user.pk).exists()


@login_required
def discussions(request, slug):
    enrolment = _enrolment_or_404(request.user, slug)
    course = enrolment.course
    form = ThreadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        t.course, t.author = course, request.user
        t.save()
        for instructor in course.instructors.all():
            notify(instructor, f"New question in {course.title}", t.title, f"/learn/{slug}/discussions/{t.pk}/", email=False)
        return redirect("learning:thread", slug=slug, pk=t.pk)
    threads = course.threads.filter(Q(is_hidden=False) | Q(author=request.user)).annotate(n=Count("posts")).select_related("author")
    return render(request, "learning/discussions.html", {"course": course, "threads": threads, "form": form})


@login_required
def thread(request, slug, pk):
    enrolment = _enrolment_or_404(request.user, slug)
    t = get_object_or_404(Thread, pk=pk, course=enrolment.course)
    moderator = _can_moderate(request.user, t.course)
    if t.is_hidden and not (moderator or t.author == request.user):
        raise Http404
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "reply" and request.POST.get("body", "").strip():
            Post.objects.create(thread=t, author=request.user, body=request.POST["body"][:10000],
                                is_instructor_answer=moderator)
            if moderator and t.is_question:
                t.is_answered = True
                t.save(update_fields=["is_answered"])
            if t.author != request.user:
                notify(t.author, f"New reply: {t.title}", "", request.path, email=False)
        elif action in ("hide", "pin") and moderator:
            if action == "hide":
                t.is_hidden = not t.is_hidden
            else:
                t.is_pinned = not t.is_pinned
            t.save()
        elif action == "hide_post" and moderator:
            Post.objects.filter(pk=request.POST.get("post"), thread=t).update(is_hidden=True)
        return redirect("learning:thread", slug=slug, pk=pk)
    posts = t.posts.select_related("author")
    if not moderator:
        posts = posts.filter(is_hidden=False)
    return render(request, "learning/thread.html", {"course": t.course, "thread": t, "posts": posts, "moderator": moderator})


@login_required
def achievements(request):
    from django.conf import settings as dj_settings

    from apps.core.models import SiteSettings

    for code in services.BADGES:  # make sure every badge exists so locked ones can be shown
        name, desc, icon = services.BADGES[code]
        Badge.objects.get_or_create(code=code, defaults={"name": name, "description": desc, "icon": icon})
    earned = {ub.badge_id: ub for ub in request.user.badges.all()}
    leaderboard = None
    if SiteSettings.load().leaderboards_enabled:
        from django.contrib.auth import get_user_model

        leaderboard = (get_user_model().objects.filter(enrolments__status="completed")
                       .annotate(n=Count("enrolments")).order_by("-n")[:10])
    return render(request, "learning/achievements.html", {
        "badges": Badge.objects.all(), "earned": earned, "streak": services.streak(request.user),
        "days": _last_28_days(request.user), "leaderboard": leaderboard,
    })


def _last_28_days(user):
    today = timezone.localdate()
    counts = dict(user.activity_days.filter(date__gt=today - timedelta(days=28)).values_list("date", "lessons_completed"))
    return [{"date": today - timedelta(days=i), "n": counts.get(today - timedelta(days=i))} for i in range(27, -1, -1)]


SOON = {
    "live": ("Live academy", "video", "Phase 2", "Live classes, webinars, office hours and recordings."),
    "labs": ("Practical labs", "flask", "Phase 2–3", "Portfolio submissions with supervisor sign-off, then coaching, refereeing and match-analysis simulators."),
    "library": ("Sports library", "library", "Phase 2", "Manuals, rules, research, theses and video archives with citation tools."),
    "assistant": ("AI study assistant", "sparkles", "Phase 3", "A tutor grounded in approved NIS material that cites sources and never gives exam answers."),
    "community": ("Careers & community", "briefcase", "Phase 3", "Mentorship, professional groups and job, internship and volunteering opportunities."),
}


@login_required
def soon(request, key):
    if key not in SOON:
        raise Http404
    title, icon, phase, text = SOON[key]
    return render(request, "learning/soon.html", {"title": title, "icon": icon, "phase": phase, "text": text})
