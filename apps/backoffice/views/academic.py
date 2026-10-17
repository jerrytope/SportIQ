from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.assessments import services as exam_services
from apps.assessments.models import Attempt, Exam, Question, QuestionBank
from apps.catalog.models import Course, Lesson, Module, ReviewComment, Subject, Track
from apps.catalog.tasks import transcode_lesson
from apps.core.audit import audit
from apps.credentials.models import CredentialType
from apps.learning import services as learning
from apps.learning.models import AcademicTerm, Application, Cohort
from apps.notifications.services import notify

from ..decorators import staff_required
from ..forms import CohortForm, CourseForm, ExamForm, LessonForm, ModuleForm, QuestionForm, TermForm

EDITORS = ("course_creator", "academic_manager", "instructor", "reviewer", "external_reviewer")


def external_only(user):
    return user.has_role("external_reviewer") and not user.has_role("course_creator", "academic_manager", "instructor", "reviewer")


def can_edit(user, course):
    if user.has_role("academic_manager"):
        return True
    if course.status in (Course.IN_REVIEW, Course.APPROVED) and not user.has_role("reviewer"):
        return False
    return course.owner_id == user.pk or course.instructors.filter(pk=user.pk).exists()


def _course_for_edit(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not can_edit(request.user, course):
        raise PermissionDenied
    return course


@staff_required(*EDITORS)
def studio(request):
    qs = Course.objects.select_related("track", "owner").annotate(n_lessons=Count("modules__lessons", distinct=True),
                                                                   n_enrolled=Count("enrolments", distinct=True))
    if external_only(request.user):
        qs = qs.filter(external_reviewers=request.user)
    elif not request.user.has_role("academic_manager", "reviewer"):
        qs = qs.filter(Q(owner=request.user) | Q(instructors=request.user)).distinct()
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(code__icontains=q))
    due = Course.objects.filter(status=Course.PUBLISHED, review_due__lte=timezone.localdate()).count()
    return render(request, "manage/studio/list.html", {"courses": qs.order_by("-updated_at"), "status": status,
                                                       "statuses": Course.STATUSES, "q": q, "review_overdue": due})


@staff_required("course_creator", "academic_manager")
def course_create(request):
    form = CourseForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        course = form.save(commit=False)
        course.owner = course.created_by = request.user
        course.save()
        form.save_m2m()
        QuestionBank.objects.create(course=course, title=f"{course.title} question bank")
        audit(request.user, "course.created", course, request=request)
        messages.success(request, "Course created as a draft. Add modules and lessons next.")
        return redirect("backoffice:course_builder", pk=course.pk)
    return render(request, "manage/studio/course_form.html", {"form": form, "creating": True})


@staff_required(*EDITORS)
def course_edit(request, pk):
    course = _course_for_edit(request, pk)
    form = CourseForm(request.POST or None, request.FILES or None, instance=course)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request.user, "course.updated", course, {"fields": form.changed_data}, request)
        messages.success(request, "Course settings saved.")
        return redirect("backoffice:course_builder", pk=pk)
    return render(request, "manage/studio/course_form.html", {"form": form, "course": course})


@staff_required(*EDITORS)
def course_builder(request, pk):
    course = get_object_or_404(Course.objects.select_related("track", "owner"), pk=pk)
    editable = can_edit(request.user, course)
    if external_only(request.user) and not course.external_reviewers.filter(pk=request.user.pk).exists():
        raise PermissionDenied
    if not editable and not request.user.has_role("reviewer", "academic_manager", "external_reviewer"):
        raise PermissionDenied
    return render(request, "manage/studio/builder.html", {
        "course": course, "modules": course.modules.prefetch_related("lessons"), "editable": editable,
        "module_form": ModuleForm(initial={"order": course.modules.count() + 1}),
        "comments": course.review_comments.select_related("author")[:20], "missing": course.metadata_missing(),
        "exams": course.exams.all(), "bank": course.question_banks.first(),
        "can_review": request.user.has_role("reviewer", "academic_manager") and course.owner_id != request.user.pk
        or request.user.has_role("academic_manager"),
        "can_publish": request.user.has_role("academic_manager"),
    })


@staff_required(*EDITORS)
@require_POST
def course_workflow(request, pk):
    course = get_object_or_404(Course, pk=pk)
    action = request.POST.get("action")
    note = request.POST.get("note", "").strip()
    user = request.user
    transitions = {
        "submit": ([Course.DRAFT], Course.IN_REVIEW, "submitted"),
        "approve": ([Course.IN_REVIEW], Course.APPROVED, "approved"),
        "changes": ([Course.IN_REVIEW, Course.APPROVED], Course.DRAFT, "changes"),
        "publish": ([Course.APPROVED, Course.PUBLISHED], Course.PUBLISHED, "published"),
        "retire": ([Course.PUBLISHED], Course.RETIRED, "retired"),
        "revise": ([Course.PUBLISHED, Course.RETIRED], Course.DRAFT, "comment"),
        "comment": (None, None, "comment"),
    }
    if action not in transitions:
        return redirect("backoffice:course_builder", pk=pk)
    if external_only(user) and (action != "comment" or not course.external_reviewers.filter(pk=user.pk).exists()):
        raise PermissionDenied
    allowed_from, to, log_action = transitions[action]
    if action == "submit":
        if not can_edit(user, course):
            raise PermissionDenied
        missing = course.metadata_missing()
        if missing or not course.lessons().exists():
            messages.error(request, "Before review, add lessons and complete: " + ", ".join(missing or ["lessons"]))
            return redirect("backoffice:course_builder", pk=pk)
    elif action in ("approve", "changes"):
        if not user.has_role("reviewer", "academic_manager"):
            raise PermissionDenied
        if course.owner_id == user.pk and not user.has_role("academic_manager"):
            messages.error(request, "You can't review your own course.")
            return redirect("backoffice:course_builder", pk=pk)
    elif action in ("publish", "retire", "revise") and not user.has_role("academic_manager"):
        raise PermissionDenied
    if allowed_from is not None and course.status not in allowed_from:
        messages.error(request, f"That action isn't available while the course is {course.get_status_display().lower()}.")
        return redirect("backoffice:course_builder", pk=pk)
    old = course.status
    if to:
        course.status = to
        if action == "publish":
            course.version += 1
            course.published_at = timezone.now()
        course.save()
    ReviewComment.objects.create(course=course, author=user, action=log_action, body=note)
    audit(user, f"course.{action}", course, {"from": old, "to": course.status, "note": note}, request)
    if course.owner and course.owner != user and action in ("approve", "changes", "publish", "comment"):
        notify(course.owner, f"{course.title}: {dict(ReviewComment.ACTIONS)[log_action]}", note,
               f"/manage/studio/{course.pk}/", email=action != "comment")
    messages.success(request, {"submit": "Submitted for academic review.", "approve": "Course approved.",
                               "changes": "Changes requested; the course is back in draft.",
                               "publish": f"Published as version {course.version}.", "retire": "Course retired. Learner records are kept.",
                               "revise": "New draft opened for revision.", "comment": "Comment added."}[action])
    return redirect("backoffice:course_builder", pk=pk)


@staff_required(*EDITORS)
@require_POST
def module_add(request, pk):
    course = _course_for_edit(request, pk)
    form = ModuleForm(request.POST)
    if form.is_valid():
        m = form.save(commit=False)
        m.course = course
        m.save()
        messages.success(request, f"Module “{m.title}” added.")
    return redirect("backoffice:course_builder", pk=pk)


@staff_required(*EDITORS)
def module_edit(request, pk):
    module = get_object_or_404(Module, pk=pk)
    _course_for_edit(request, module.course_id)
    if request.method == "POST" and request.POST.get("action") == "delete":
        if module.lessons.filter(progress_records__isnull=False).exists():
            messages.error(request, "This module has lessons with learner progress. Retire the course instead.")
        else:
            module.delete()
            messages.success(request, "Module deleted.")
        return redirect("backoffice:course_builder", pk=module.course_id)
    form = ModuleForm(request.POST or None, instance=module)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("backoffice:course_builder", pk=module.course_id)
    return render(request, "manage/studio/simple_form.html", {"form": form, "title": f"Edit module: {module.title}",
                                                              "back": module.course_id, "delete": True})


@staff_required(*EDITORS)
def lesson_edit(request, pk=None, module_id=None):
    if pk:
        lesson = get_object_or_404(Lesson.objects.select_related("module__course"), pk=pk)
        module = lesson.module
    else:
        module = get_object_or_404(Module, pk=module_id)
        lesson = Lesson(module=module, order=module.lessons.count() + 1)
    course = _course_for_edit(request, module.course_id)
    old_video = lesson.video.name if lesson.pk else ""
    form = LessonForm(request.POST or None, request.FILES or None, instance=lesson, course=course)
    if request.method == "POST" and form.is_valid():
        lesson = form.save()
        if lesson.video and lesson.video.name != old_video:
            Lesson.objects.filter(pk=lesson.pk).update(media_status="processing", hls_playlist="")
            transcode_lesson.delay(lesson.pk)
            messages.info(request, "Video uploaded. Low-bandwidth versions are being generated.")
        messages.success(request, "Lesson saved.")
        return redirect("backoffice:course_builder", pk=course.pk)
    return render(request, "manage/studio/lesson_form.html", {"form": form, "lesson": lesson, "course": course, "module": module})


@staff_required(*EDITORS)
@require_POST
def lesson_delete(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    course = _course_for_edit(request, lesson.module.course_id)
    if lesson.progress_records.exists():
        messages.error(request, "Learners have progress on this lesson, so it can't be deleted. Edit it instead.")
    else:
        lesson.delete()
        messages.success(request, "Lesson deleted.")
    return redirect("backoffice:course_builder", pk=course.pk)


@staff_required(*EDITORS)
def question_bank(request, pk):
    course = get_object_or_404(Course, pk=pk)
    bank, _ = QuestionBank.objects.get_or_create(course=course, defaults={"title": f"{course.title} question bank"})
    editable = can_edit(request.user, course) or request.user.has_role("instructor")
    form = QuestionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and editable and form.is_valid():
        q = form.save(commit=False)
        q.bank = bank
        q.save()
        form.instance = q
        form.save()
        messages.success(request, "Question added.")
        return redirect("backoffice:question_bank", pk=pk)
    topic = request.GET.get("topic")
    questions = bank.questions.prefetch_related("choices")
    if topic:
        questions = questions.filter(topic=topic)
    return render(request, "manage/studio/questions.html", {
        "course": course, "bank": bank, "questions": questions, "form": form, "editable": editable,
        "topics": bank.questions.exclude(topic="").values("topic").annotate(n=Count("pk")).order_by("topic"),
    })


@staff_required(*EDITORS)
def question_edit(request, pk):
    q = get_object_or_404(Question.objects.select_related("bank__course"), pk=pk)
    course = q.bank.course
    if not (can_edit(request.user, course) or request.user.has_role("instructor")):
        raise PermissionDenied
    form = QuestionForm(request.POST or None, request.FILES or None, instance=q)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Question updated.")
        return redirect("backoffice:question_bank", pk=course.pk)
    return render(request, "manage/studio/simple_form.html", {"form": form, "title": "Edit question", "back": course.pk})


@staff_required(*EDITORS)
def exam_edit(request, pk):
    course = _course_for_edit(request, pk)
    bank, _ = QuestionBank.objects.get_or_create(course=course, defaults={"title": f"{course.title} question bank"})
    exam = Exam.objects.filter(course=course, pk=request.GET.get("exam")).first() or Exam.objects.filter(course=course, is_final=True).first()
    exam = exam or Exam(course=course, bank=bank, title=f"{course.title}: final assessment", is_final=True)
    form = ExamForm(request.POST or None, instance=exam)
    if request.method == "POST" and form.is_valid():
        e = form.save(commit=False)
        e.course, e.bank = course, bank
        e.save()
        audit(request.user, "exam.saved", e, {"fields": form.changed_data}, request)
        messages.success(request, "Assessment saved. Attach it to a quiz lesson so learners can take it.")
        return redirect("backoffice:course_builder", pk=pk)
    return render(request, "manage/studio/simple_form.html", {
        "form": form, "title": "Assessment settings", "back": pk,
        "help": f"The question bank has {bank.questions.filter(is_active=True).count()} active questions. "
                "Each attempt draws the number of questions set below, optionally by topic blueprint, "
                "e.g. {\"Anti-doping rules\": 4}.",
    })


@staff_required("reviewer", "academic_manager", "external_reviewer")
def review_queue(request):
    in_review = Course.objects.filter(status=Course.IN_REVIEW).select_related("owner", "track")
    if external_only(request.user):
        in_review = in_review.filter(external_reviewers=request.user)
    return render(request, "manage/studio/review_queue.html", {
        "in_review": in_review,
        "approved": Course.objects.filter(status=Course.APPROVED).select_related("owner", "track"),
        "overdue": Course.objects.filter(status=Course.PUBLISHED, review_due__lte=timezone.localdate()),
    })


# --- Assessment centre ----------------------------------------------------------------

@staff_required("instructor", "academic_manager")
def marking(request):
    qs = Attempt.objects.select_related("exam__course", "user")
    if not request.user.has_role("academic_manager"):
        qs = qs.filter(Q(exam__course__instructors=request.user) | Q(exam__course__owner=request.user)).distinct()
    if request.method == "POST" and request.POST.get("action") == "release_all":
        n = 0
        skipped = 0
        for att in qs.filter(status=Attempt.MARKED):
            try:
                exam_services.release(att, request.user)
                n += 1
            except ValueError:
                skipped += 1
        messages.success(request, f"Released {n} result(s)." + (f" {skipped} need moderation first." if skipped else ""))
        return redirect("backoffice:marking")
    return render(request, "manage/assessments/queue.html", {
        "to_mark": qs.filter(status=Attempt.SUBMITTED), "to_release": qs.filter(status=Attempt.MARKED),
        "recent": qs.filter(status=Attempt.RELEASED)[:20],
        "exams": Exam.objects.select_related("course").annotate(n=Count("attempts")),
    })


@staff_required("instructor", "academic_manager")
def mark_attempt(request, pk):
    att = get_object_or_404(Attempt.objects.select_related("exam__course", "user"), pk=pk)
    responses = att.responses.select_related("question").prefetch_related("question__choices", "question__rubric", "selected")
    if request.method == "POST":
        if request.POST.get("action") == "release" and att.status == Attempt.MARKED:
            try:
                exam_services.release(att, request.user)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("backoffice:mark_attempt", pk=pk)
            messages.success(request, "Result released to the learner.")
            return redirect("backoffice:marking")
        for r in responses:
            if r.question.is_auto_marked:
                continue
            raw = request.POST.get(f"score_{r.pk}")
            if raw not in (None, ""):
                exam_services.mark_response(r, raw, request.POST.get(f"feedback_{r.pk}", ""), request.user)
        audit(request.user, "exam.marked", att, request=request)
        att.refresh_from_db()
        messages.success(request, "Marks saved." + (" All questions marked. Release when ready." if att.status == Attempt.MARKED else ""))
        return redirect("backoffice:mark_attempt", pk=pk)
    return render(request, "manage/assessments/mark.html", {"attempt": att, "responses": responses,
                                                            "selected": {r.pk: set(c.pk for c in r.selected.all()) for r in responses}})


@staff_required("instructor", "academic_manager")
def item_analysis(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    attempts = exam.attempts.filter(status=Attempt.RELEASED)
    return render(request, "manage/assessments/analysis.html", {
        "exam": exam, "rows": exam_services.item_analysis(exam), "n": attempts.count(),
        "pass_rate": round(100 * attempts.filter(passed=True).count() / attempts.count()) if attempts.count() else 0,
    })


# --- Admissions, cohorts, academic settings ----------------------------------------------

@staff_required("academic_manager")
def admissions(request):
    status = request.GET.get("status", "open")
    qs = Application.objects.select_related("user", "course")
    qs = qs.filter(status__in=["submitted", "review"]) if status == "open" else qs.filter(status=status)
    return render(request, "manage/admissions.html", {"applications": qs, "status": status})


@staff_required("academic_manager")
@require_POST
def admission_decide(request, pk):
    app = get_object_or_404(Application, pk=pk)
    decision = request.POST.get("decision")
    if decision not in ("admitted", "rejected", "review"):
        return redirect("backoffice:admissions")
    app.status = decision
    app.decision_note = request.POST.get("note", "")
    app.eligibility_met = decision == "admitted" or (False if decision == "rejected" else None)
    app.decided_by, app.decided_at = request.user, timezone.now()
    app.save()
    audit(request.user, f"admission.{decision}", app, {"note": app.decision_note}, request)
    if decision == "admitted":
        if app.course.is_free:
            learning.enrol(app.user, app.course, source="admin")
        notify(app.user, f"Admitted: {app.course.title}", app.decision_note or "Congratulations!", app.course.get_absolute_url())
    elif decision == "rejected":
        notify(app.user, f"Application outcome: {app.course.title}", app.decision_note or "Your application was not successful this time.",
               "/learn/courses/?tab=applications")
    messages.success(request, f"Application {app.get_status_display().lower()}.")
    return redirect("backoffice:admissions")


@staff_required("academic_manager")
def cohorts(request):
    form = CohortForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        messages.success(request, f"Cohort “{c.name}” created.")
        return redirect("backoffice:cohort_detail", pk=c.pk)
    return render(request, "manage/cohorts.html", {
        "cohorts": Cohort.objects.select_related("course", "institution", "term").annotate(n=Count("enrolments")),
        "form": form,
    })


@staff_required("academic_manager")
def cohort_detail(request, pk):
    cohort = get_object_or_404(Cohort.objects.select_related("course"), pk=pk)
    if request.method == "POST":
        emails = [e.strip().lower() for e in request.POST.get("emails", "").replace(",", "\n").splitlines() if e.strip()]
        due = request.POST.get("due_date") or None
        added, missing = 0, []
        for email in emails:
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                missing.append(email)
                continue
            if cohort.capacity and cohort.enrolments.count() >= cohort.capacity:
                messages.warning(request, "Cohort is full.")
                break
            enr, _ = learning.enrol(user, cohort.course, source="admin", cohort=cohort, due_date=due)
            if enr.cohort_id != cohort.pk:
                enr.cohort = cohort
                enr.save(update_fields=["cohort"])
            added += 1
        audit(request.user, "cohort.bulk_enrol", cohort, {"added": added, "missing": missing}, request)
        messages.success(request, f"Enrolled {added} learner(s).")
        if missing:
            messages.warning(request, "No account for: " + ", ".join(missing[:20]))
        return redirect("backoffice:cohort_detail", pk=pk)
    return render(request, "manage/cohort_detail.html", {"cohort": cohort,
                                                         "enrolments": cohort.enrolments.select_related("user")})


@staff_required("academic_manager")
def academic(request):
    term_form = TermForm(request.POST if request.POST.get("form") == "term" else None)
    if request.method == "POST":
        form = request.POST.get("form")
        if form == "term" and term_form.is_valid():
            term_form.save()
            messages.success(request, "Academic term added.")
        elif form == "track" and request.POST.get("name"):
            Track.objects.get_or_create(name=request.POST["name"].strip(), defaults={"description": request.POST.get("description", "")})
            messages.success(request, "Subject area added.")
        elif form == "subject" and request.POST.get("name") and request.POST.get("track"):
            Subject.objects.get_or_create(track_id=request.POST["track"], name=request.POST["name"].strip())
            messages.success(request, "Subject added.")
        return redirect("backoffice:academic")
    return render(request, "manage/academic.html", {
        "terms": AcademicTerm.objects.all(), "term_form": term_form,
        "tracks": Track.objects.prefetch_related("subjects").annotate(n=Count("courses")),
        "credential_types": CredentialType.objects.all(),
    })
