from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.notifications.services import notify

from .models import ActivityDay, Badge, Enrolment, LessonProgress, UserBadge

BADGES = {
    "first-lesson": ("First whistle", "Completed your first lesson", "▶"),
    "first-course": ("Full time", "Completed your first course", "🏆"),
    "streak-3": ("Hat-trick", "Learned three days in a row", "🔥"),
    "streak-7": ("Match fit", "Learned seven days in a row", "💪"),
    "exam-pass": ("Passed with merit", "Passed an exam", "✔"),
    "five-courses": ("Squad depth", "Completed five courses", "⭐"),
}


def award(user, code):
    name, desc, icon = BADGES[code]
    badge, _ = Badge.objects.get_or_create(code=code, defaults={"name": name, "description": desc, "icon": icon})
    ub, created = UserBadge.objects.get_or_create(user=user, badge=badge)
    if created:
        notify(user, f"Badge earned: {badge.name}", badge.description, "/learn/achievements/", email=False)
    return created


def prerequisites_missing(user, course):
    done = set(Enrolment.objects.filter(user=user, status="completed").values_list("course_id", flat=True))
    return [c for c in course.prerequisites.all() if c.pk not in done]


@transaction.atomic
def enrol(user, course, source="self", cohort=None, due_date=None):
    enrolment, created = Enrolment.objects.get_or_create(
        user=user, course=course,
        defaults={"source": source, "cohort": cohort, "course_version": max(course.version, 1), "due_date": due_date},
    )
    if not created and enrolment.status == "withdrawn":
        enrolment.status = "active"
        enrolment.save(update_fields=["status"])
    if created:
        notify(user, f"You're enrolled: {course.title}", "Start your first lesson whenever you're ready.",
               course.get_absolute_url())
        from apps.integrations.services import emit

        transaction.on_commit(lambda: emit("enrolment.created", user, {"course": course.slug, "user": user.email,
                                                                       "source": source}))
    return enrolment, created


def streak(user):
    days = set(ActivityDay.objects.filter(user=user, date__gte=timezone.localdate() - timedelta(days=60))
               .values_list("date", flat=True))
    count, day = 0, timezone.localdate()
    if day not in days:
        day -= timedelta(days=1)
    while day in days:
        count += 1
        day -= timedelta(days=1)
    return count


def record_activity(user, lessons=0):
    day, _ = ActivityDay.objects.get_or_create(user=user, date=timezone.localdate())
    if lessons:
        day.lessons_completed += lessons
        day.save(update_fields=["lessons_completed"])
    s = streak(user)
    if s >= 3:
        award(user, "streak-3")
    if s >= 7:
        award(user, "streak-7")


def touch(enrolment, lesson, position=None):
    progress, _ = LessonProgress.objects.get_or_create(enrolment=enrolment, lesson=lesson)
    if position is not None:
        progress.position_seconds = int(position)
        progress.save(update_fields=["position_seconds", "updated_at"])
    enrolment.last_lesson = lesson
    enrolment.last_activity_at = timezone.now()
    enrolment.save(update_fields=["last_lesson", "last_activity_at"])
    record_activity(enrolment.user)
    return progress


@transaction.atomic
def complete_lesson(enrolment, lesson):
    progress, _ = LessonProgress.objects.get_or_create(enrolment=enrolment, lesson=lesson)
    if not progress.completed:
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save()
        record_activity(enrolment.user, lessons=1)
        award(enrolment.user, "first-lesson")
    enrolment.recompute_progress()
    enrolment.last_lesson = lesson
    enrolment.last_activity_at = timezone.now()
    enrolment.save(update_fields=["progress", "last_lesson", "last_activity_at"])
    check_completion(enrolment)
    return progress


def final_exam_passed(enrolment):
    exam = enrolment.course.final_exam()
    if not exam:
        return True
    return exam.attempts.filter(user=enrolment.user, passed=True, status="released").exists()


def check_completion(enrolment):
    """Completion rule: all lessons done and, where required, the final exam passed and released."""
    if enrolment.status == "completed":
        return True
    course = enrolment.course
    if enrolment.recompute_progress() < 100:
        return False
    if course.completion_requires_exam and not final_exam_passed(enrolment):
        return False
    enrolment.status = "completed"
    enrolment.completed_at = timezone.now()
    enrolment.save(update_fields=["status", "completed_at", "progress"])
    award(enrolment.user, "first-course")
    from apps.credentials.services import check_programmes, record_cpd
    from apps.integrations.services import emit

    record_cpd(enrolment.user, f"Course: {course.title}", "course", course.duration_hours, f"course:{course.pk}")
    emit("enrolment.completed", enrolment.user, {"course": course.slug, "user": enrolment.user.email,
                                                 "completed_at": enrolment.completed_at.isoformat()})
    if Enrolment.objects.filter(user=enrolment.user, status="completed").count() >= 5:
        award(enrolment.user, "five-courses")
    if course.issues_certificate:
        from apps.credentials.services import issue_for_enrolment

        issue_for_enrolment(enrolment)
    else:
        notify(enrolment.user, f"Course completed: {course.title}", "Well done!", "/learn/")
    check_programmes(enrolment.user)
    return True


def next_lesson(enrolment):
    done = set(enrolment.lesson_progress.filter(completed=True).values_list("lesson_id", flat=True))
    for lesson in enrolment.course.lessons():
        if lesson.pk not in done:
            return lesson
    return None
