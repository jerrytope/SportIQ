from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


def unique_slug(instance, value, field="slug", max_length=200):
    base = slugify(value)[: max_length - 6] or "item"
    slug, n = base, 2
    Model = type(instance)
    while Model.objects.filter(**{field: slug}).exclude(pk=instance.pk).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Sport(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *a, **kw):
        self.slug = self.slug or slugify(self.name)
        super().save(*a, **kw)


class Profession(models.Model):
    """User categories from blueprint §2 (coaches, referees, administrators, ...)."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    plural = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=40, blank=True, help_text="Icon name used on the landing page")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *a, **kw):
        self.slug = self.slug or slugify(self.name)
        super().save(*a, **kw)


class Track(models.Model):
    """Curriculum track (blueprint Module 2)."""

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *a, **kw):
        self.slug = self.slug or slugify(self.name)
        super().save(*a, **kw)


class Subject(models.Model):
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["track", "name"]
        unique_together = [("track", "name")]

    def __str__(self):
        return self.name


LEVELS = [("intro", "Introductory"), ("beginner", "Beginner"), ("intermediate", "Intermediate"),
          ("advanced", "Advanced"), ("specialist", "Specialist")]
FORMATS = [("self_paced", "Self-paced online"), ("cohort", "Instructor-led cohort"), ("blended", "Blended (online + in-person)")]
LANGUAGES = [("en", "English"), ("pcm", "Nigerian Pidgin"), ("yo", "Yoruba"), ("ha", "Hausa"), ("ig", "Igbo")]


class CourseQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Course.PUBLISHED)

    def visible_to(self, user):
        qs = self.published()
        if not (user and user.is_authenticated):
            return qs.filter(is_public=True)
        return qs


class Course(TimeStampedModel):
    DRAFT, IN_REVIEW, APPROVED, PUBLISHED, RETIRED = "draft", "in_review", "approved", "published", "retired"
    STATUSES = [(DRAFT, "Draft"), (IN_REVIEW, "In review"), (APPROVED, "Approved"),
                (PUBLISHED, "Published"), (RETIRED, "Retired")]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    code = models.CharField(max_length=20, blank=True, help_text="e.g. NIS-COA-101")
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    track = models.ForeignKey(Track, on_delete=models.PROTECT, related_name="courses")
    subject = models.ForeignKey(Subject, null=True, blank=True, on_delete=models.SET_NULL)
    sports = models.ManyToManyField(Sport, blank=True, related_name="courses",
                                    help_text="Leave empty for courses relevant to all sports")
    professions = models.ManyToManyField(Profession, blank=True, related_name="courses")
    level = models.CharField(max_length=20, choices=LEVELS, default="beginner")
    language = models.CharField(max_length=5, choices=LANGUAGES, default="en")
    delivery_format = models.CharField(max_length=20, choices=FORMATS, default="self_paced")
    duration_hours = models.DecimalField(max_digits=5, decimal_places=1, default=2)
    thumbnail = models.ImageField(upload_to="courses/", blank=True)
    cover_color = models.CharField(max_length=7, default="#008751", help_text="Used when there is no thumbnail")
    price_kobo = models.PositiveIntegerField(default=0, help_text="0 = free. Amount in kobo (₦1 = 100 kobo)")
    is_public = models.BooleanField(default=True, help_text="Visible to anonymous visitors in the catalogue")
    requires_application = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    prerequisites = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="unlocks")
    institution = models.ForeignKey("institutions.Institution", null=True, blank=True, on_delete=models.SET_NULL,
                                    help_text="Delivering institution (NIS or partner)")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                              related_name="owned_courses")
    instructors = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="teaching_courses")
    # Quality-assurance metadata required for every course (blueprint Module 16)
    objectives = models.TextField(blank=True, help_text="One learning objective per line")
    audience = models.TextField(blank=True)
    prerequisites_text = models.TextField("Entry requirements", blank=True)
    assessment_criteria = models.TextField(blank=True)
    references = models.TextField(blank=True)
    framework_mapping = models.CharField(max_length=255, blank=True,
                                         help_text="Professional standard / international framework mapped")
    revision_date = models.DateField(null=True, blank=True)
    review_due = models.DateField(null=True, blank=True)
    # Completion rules
    completion_requires_exam = models.BooleanField(default=True)
    issues_certificate = models.BooleanField(default=True)
    credential_type = models.ForeignKey("credentials.CredentialType", null=True, blank=True,
                                        on_delete=models.SET_NULL)
    # Workflow & versioning
    status = models.CharField(max_length=12, choices=STATUSES, default=DRAFT, db_index=True)
    version = models.PositiveIntegerField(default=0, help_text="Increments each time the course is published")
    published_at = models.DateTimeField(null=True, blank=True)
    publish_at = models.DateTimeField(null=True, blank=True, help_text="Scheduled publication (approved courses only)")
    external_reviewers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="reviewing_courses",
                                                help_text="External subject experts invited to review this course")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name="created_courses")

    objects = CourseQuerySet.as_manager()

    class Meta:
        ordering = ["-featured", "title"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("catalog:course_detail", args=[self.slug])

    @property
    def is_free(self):
        return self.price_kobo == 0

    @property
    def price_naira(self):
        return self.price_kobo / 100

    @property
    def objectives_list(self):
        return [o.strip() for o in self.objectives.splitlines() if o.strip()]

    def lessons(self):
        return Lesson.objects.filter(module__course=self).order_by("module__order", "order", "pk")

    @property
    def lesson_count(self):
        return self.lessons().count()

    def final_exam(self):
        from apps.assessments.models import Exam

        return Exam.objects.filter(course=self, is_final=True, is_published=True).first()

    def translation_for(self, language):
        if not language or language.startswith("en"):
            return None
        return self.translations.filter(language=language, status="approved").first()

    def metadata_missing(self):
        """Fields that must be filled before submitting for review."""
        required = {"objectives": "Objectives", "audience": "Audience", "assessment_criteria": "Assessment criteria",
                    "references": "References", "revision_date": "Revision date", "review_due": "Review date"}
        return [label for f, label in required.items() if not getattr(self, f)]


class ReviewComment(models.Model):
    ACTIONS = [("comment", "Comment"), ("submitted", "Submitted for review"), ("approved", "Approved"),
               ("changes", "Changes requested"), ("published", "Published"), ("retired", "Retired")]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="review_comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=12, choices=ACTIONS, default="comment")
    body = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.title


class Lesson(models.Model):
    KINDS = [("video", "Video"), ("reading", "Reading"), ("download", "Downloadable resource"),
             ("quiz", "Quiz / assessment"), ("practical", "Practical task / portfolio"), ("lab", "Practical lab / simulation"),
             ("scorm", "SCORM / interactive package"), ("live", "Live session")]
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=KINDS, default="video")
    body = models.TextField(blank=True, help_text="Markdown. For video lessons this is the text alternative.")
    video = models.FileField(upload_to="lessons/video/", blank=True)
    hls_playlist = models.CharField(max_length=255, blank=True, help_text="Set by the transcoding job")
    audio = models.FileField(upload_to="lessons/audio/", blank=True, help_text="Audio-only version (low bandwidth)")
    poster = models.ImageField(upload_to="lessons/posters/", blank=True)
    subtitles = models.FileField(upload_to="lessons/subtitles/", blank=True, help_text="WebVTT (.vtt)")
    transcript = models.TextField(blank=True)
    attachment = models.FileField(upload_to="lessons/files/", blank=True)
    exam = models.ForeignKey("assessments.Exam", null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="lessons")
    practical_task = models.ForeignKey("practicals.PracticalTask", null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="lessons")
    lab = models.ForeignKey("labs.Scenario", null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons")
    live_session = models.ForeignKey("live.LiveSession", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="lessons")
    embed_url = models.URLField(blank=True, help_text="Interactive content (H5P, simulation) shown in an embedded frame")
    duration_minutes = models.PositiveSmallIntegerField(default=10)
    is_preview = models.BooleanField(default=False, help_text="Free preview for visitors")
    MEDIA_STATUSES = [("none", "No media"), ("processing", "Processing"), ("ready", "Ready"), ("failed", "Failed")]
    media_status = models.CharField(max_length=12, choices=MEDIA_STATUSES, default="none")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.title

    @property
    def course(self):
        return self.module.course

    def get_absolute_url(self):
        return reverse("learning:lesson", args=[self.module.course.slug, self.pk])


class LearningPath(TimeStampedModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    profession = models.ForeignKey(Profession, null=True, blank=True, on_delete=models.SET_NULL)
    track = models.ForeignKey(Track, null=True, blank=True, on_delete=models.SET_NULL)
    is_published = models.BooleanField(default=True)
    cover_color = models.CharField(max_length=7, default="#0B3D2E")

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("catalog:path_detail", args=[self.slug])


class LearningPathItem(models.Model):
    path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="items")
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    stage = models.CharField(max_length=20, choices=LEVELS, default="beginner")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class LessonTemplate(models.Model):
    """Reusable lesson structures for the content studio."""

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=Lesson.KINDS, default="reading")
    body = models.TextField()
    duration_minutes = models.PositiveSmallIntegerField(default=10)

    def __str__(self):
        return self.name


class CourseTranslation(TimeStampedModel):
    """Phase 4: translated course text. Shown only once an expert reviewer approves it."""

    STATUSES = [("draft", "Draft (machine-assisted)"), ("review", "In expert review"), ("approved", "Approved")]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="translations")
    language = models.CharField(max_length=5, choices=LANGUAGES)
    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="draft")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = [("course", "language")]


class LessonTranslation(TimeStampedModel):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="translations")
    language = models.CharField(max_length=5, choices=LANGUAGES)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    subtitles = models.FileField(upload_to="lessons/subtitles/", blank=True)
    status = models.CharField(max_length=10, choices=CourseTranslation.STATUSES, default="draft")

    class Meta:
        unique_together = [("lesson", "language")]
