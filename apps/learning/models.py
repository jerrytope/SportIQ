from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.catalog.models import Course, Lesson
from apps.core.models import TimeStampedModel


class AcademicTerm(models.Model):
    name = models.CharField(max_length=80)
    starts_on = models.DateField()
    ends_on = models.DateField()

    class Meta:
        ordering = ["-starts_on"]

    def __str__(self):
        return self.name


class Cohort(TimeStampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="cohorts")
    name = models.CharField(max_length=120)
    term = models.ForeignKey(AcademicTerm, null=True, blank=True, on_delete=models.SET_NULL)
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.SET_NULL)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    leaderboard_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-starts_on", "name"]

    def __str__(self):
        return f"{self.course} — {self.name}"


class Enrolment(TimeStampedModel):
    SOURCES = [("self", "Self-enrolled"), ("paid", "Paid"), ("nominated", "Nominated by institution"),
               ("sponsored", "Sponsored / scholarship"), ("admin", "Enrolled by admin")]
    STATUSES = [("active", "In progress"), ("completed", "Completed"), ("withdrawn", "Withdrawn")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrolments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrolments")
    course_version = models.PositiveIntegerField(default=1)
    cohort = models.ForeignKey(Cohort, null=True, blank=True, on_delete=models.SET_NULL, related_name="enrolments")
    source = models.CharField(max_length=10, choices=SOURCES, default="self")
    status = models.CharField(max_length=10, choices=STATUSES, default="active", db_index=True)
    progress = models.PositiveSmallIntegerField(default=0, help_text="Percent of lessons completed")
    last_lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_activity_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("user", "course")]
        ordering = ["-last_activity_at", "-created_at"]

    def __str__(self):
        return f"{self.user} → {self.course}"

    def recompute_progress(self):
        total = self.course.lessons().count()
        done = self.lesson_progress.filter(completed=True, lesson__module__course=self.course).count()
        self.progress = round(100 * done / total) if total else 0
        return self.progress


class LessonProgress(models.Model):
    enrolment = models.ForeignKey(Enrolment, on_delete=models.CASCADE, related_name="lesson_progress")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress_records")
    completed = models.BooleanField(default=False)
    position_seconds = models.PositiveIntegerField(default=0, help_text="Resume point for video")
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("enrolment", "lesson")]


class Note(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notes")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="notes")
    body = models.TextField()
    at_seconds = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["at_seconds", "created_at"]


class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="bookmarks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "lesson")]
        ordering = ["-created_at"]


class Thread(TimeStampedModel):
    """Course discussion thread or moderated Q&A question."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="threads")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="threads")
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_question = models.BooleanField(default=True)
    is_answered = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title


class Post(TimeStampedModel):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    is_instructor_answer = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]


class CourseFeedback(TimeStampedModel):
    enrolment = models.OneToOneField(Enrolment, on_delete=models.CASCADE, related_name="feedback")
    course_rating = models.PositiveSmallIntegerField()
    instructor_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    relevance_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True)


class Application(TimeStampedModel):
    """Admission application for courses/programmes that require one."""

    STATUSES = [("submitted", "Submitted"), ("review", "Under review"), ("admitted", "Admitted"),
                ("rejected", "Not admitted"), ("withdrawn", "Withdrawn")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="applications")
    statement = models.TextField(help_text="Why you want to take this programme and relevant experience")
    document = models.FileField(upload_to="applications/", blank=True)
    eligibility_met = models.BooleanField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="submitted", db_index=True)
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("user", "course")]


class Nomination(TimeStampedModel):
    """A federation / state council nominates a member onto a course (blueprint §2)."""

    STATUSES = [("pending", "Pending"), ("enrolled", "Enrolled"), ("declined", "Declined")]
    institution = models.ForeignKey("institutions.Institution", on_delete=models.CASCADE, related_name="nominations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="nominations")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="nominations")
    nominated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="pending")

    class Meta:
        ordering = ["-created_at"]


# --- Gamification (blueprint Module 15) -------------------------------------------------

class Badge(models.Model):
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200)
    icon = models.CharField(max_length=8, default="★")

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    awarded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("user", "badge")]
        ordering = ["-awarded_at"]


class ActivityDay(models.Model):
    """One row per user per day with learning activity; used for streaks and active-learner metrics."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_days")
    date = models.DateField(default=timezone.localdate, db_index=True)
    lessons_completed = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("user", "date")]
