import random

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class QuestionBank(TimeStampedModel):
    course = models.ForeignKey("catalog.Course", on_delete=models.CASCADE, related_name="question_banks")
    title = models.CharField(max_length=200)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class Question(TimeStampedModel):
    MCQ, MULTI, TF, SHORT, ESSAY, CASE = "mcq", "multi", "tf", "short", "essay", "case"
    KINDS = [(MCQ, "Multiple choice (one answer)"), (MULTI, "Multiple select"), (TF, "True / false"),
             (SHORT, "Short answer"), (ESSAY, "Essay"), (CASE, "Case study (scenario + written answer)")]
    AUTO_MARKED = {MCQ, MULTI, TF}
    DIFFICULTIES = [(1, "Easy"), (2, "Medium"), (3, "Hard")]

    bank = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name="questions")
    kind = models.CharField(max_length=6, choices=KINDS, default=MCQ)
    text = models.TextField()
    image = models.ImageField(upload_to="questions/", blank=True)
    video = models.FileField(upload_to="questions/video/", blank=True, help_text="Video clip shown with the question")
    case_text = models.TextField(blank=True, help_text="Scenario text for case-study questions")
    topic = models.CharField(max_length=80, blank=True)
    difficulty = models.PositiveSmallIntegerField(choices=DIFFICULTIES, default=2)
    points = models.PositiveSmallIntegerField(default=1)
    explanation = models.TextField(blank=True, help_text="Shown after results are released")
    model_answer = models.TextField(blank=True, help_text="Guidance for markers (written questions)")
    is_active = models.BooleanField(default=True)
    is_practice = models.BooleanField(default=False, help_text="Practice-only: never drawn into graded exams")
    ai_draft = models.BooleanField(default=False, help_text="Drafted by the AI copilot; needs expert review")

    class Meta:
        ordering = ["topic", "pk"]

    def __str__(self):
        return self.text[:80]

    @property
    def is_auto_marked(self):
        return self.kind in self.AUTO_MARKED


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.text


class RubricCriterion(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="rubric")
    title = models.CharField(max_length=200)
    max_points = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["pk"]


class Exam(TimeStampedModel):
    course = models.ForeignKey("catalog.Course", on_delete=models.CASCADE, related_name="exams")
    bank = models.ForeignKey(QuestionBank, on_delete=models.PROTECT, related_name="exams")
    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True)
    time_limit_minutes = models.PositiveSmallIntegerField(default=30)
    pass_mark = models.PositiveSmallIntegerField(default=70, help_text="Percent")
    attempts_allowed = models.PositiveSmallIntegerField(default=3)
    question_count = models.PositiveSmallIntegerField(default=10, help_text="Questions drawn per attempt")
    blueprint = models.JSONField(default=dict, blank=True,
                                 help_text='Optional topic → count, e.g. {"Anti-doping rules": 4}')
    shuffle = models.BooleanField(default=True)
    is_final = models.BooleanField(default=False, help_text="Counts towards course completion")
    is_pretest = models.BooleanField(default=False, help_text="Ungraded baseline test used for impact evaluation")
    opens_at = models.DateTimeField(null=True, blank=True, help_text="Scheduled window (optional)")
    closes_at = models.DateTimeField(null=True, blank=True)
    requires_moderation = models.BooleanField(default=False, help_text="A second marker must moderate before release")
    webcam_invigilation = models.BooleanField(default=False, help_text="Periodic webcam snapshots (consent + alternative offered)")
    identity_declaration = models.BooleanField(default=True, help_text="Learner confirms identity and own work before starting")
    auto_release = models.BooleanField(default=True, help_text="Release results immediately when fully auto-marked")
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["course", "title"]

    def __str__(self):
        return self.title

    def draw_questions(self):
        pool = list(self.bank.questions.filter(is_active=True, is_practice=False, ai_draft=False))
        chosen = []
        for topic, count in (self.blueprint or {}).items():
            topical = [q for q in pool if q.topic == topic and q not in chosen]
            chosen += random.sample(topical, min(int(count), len(topical)))
        rest = [q for q in pool if q not in chosen]
        need = max(0, self.question_count - len(chosen))
        chosen += random.sample(rest, min(need, len(rest)))
        if self.shuffle:
            random.shuffle(chosen)
        else:
            chosen.sort(key=lambda q: q.pk)
        return chosen

    def is_open_now(self):
        now = timezone.now()
        return (not self.opens_at or self.opens_at <= now) and (not self.closes_at or now <= self.closes_at)

    def allowed_attempts(self, user):
        extra = sum(self.extensions.filter(user=user).values_list("extra_attempts", flat=True))
        return self.attempts_allowed + extra

    def attempts_for(self, user):
        return self.attempts.filter(user=user).exclude(status=Attempt.IN_PROGRESS)


class Attempt(TimeStampedModel):
    IN_PROGRESS, SUBMITTED, MARKED, RELEASED = "in_progress", "submitted", "marked", "released"
    STATUSES = [(IN_PROGRESS, "In progress"), (SUBMITTED, "Awaiting marking"), (MARKED, "Marked"),
                (RELEASED, "Results released")]
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveSmallIntegerField(default=1)
    started_at = models.DateTimeField(default=timezone.now)
    deadline = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default=IN_PROGRESS, db_index=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    percent = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    passed = models.BooleanField(null=True)
    released_at = models.DateTimeField(null=True, blank=True)
    integrity_flags = models.JSONField(default=list, blank=True, help_text="e.g. tab switches, late sync")
    moderated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    moderation_note = models.TextField(blank=True)
    similarity_flag = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True,
                                          help_text="Highest % overlap of written answers with another attempt")
    accessible_alternative = models.BooleanField(default=False, help_text="Sat with an alternative arrangement")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user} — {self.exam} #{self.number}"

    @property
    def seconds_left(self):
        return max(0, int((self.deadline - timezone.now()).total_seconds()))

    @property
    def is_open(self):
        return self.status == self.IN_PROGRESS and self.seconds_left > 0


class Response(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    order = models.PositiveSmallIntegerField(default=0)
    selected = models.ManyToManyField(Choice, blank=True)
    text = models.TextField(blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rubric_scores = models.JSONField(default=dict, blank=True)
    feedback = models.TextField(blank=True)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order"]
        unique_together = [("attempt", "question")]

    @property
    def needs_marking(self):
        return not self.question.is_auto_marked and self.score is None


class ExamExtension(models.Model):
    """Extra attempts granted (resit approved or appeal upheld)."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="extensions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_extensions")
    extra_attempts = models.PositiveSmallIntegerField(default=1)
    reason = models.CharField(max_length=255)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)


class Appeal(TimeStampedModel):
    KINDS = [("result", "Appeal a result"), ("resit", "Request a resit"), ("access", "Request an accessible alternative")]
    STATUSES = [("open", "Open"), ("upheld", "Upheld"), ("dismissed", "Dismissed")]
    attempt = models.ForeignKey(Attempt, null=True, blank=True, on_delete=models.CASCADE, related_name="appeals")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="appeals")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appeals")
    kind = models.CharField(max_length=8, choices=KINDS, default="result")
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUSES, default="open", db_index=True)
    outcome = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["-created_at"]


class InvigilationSnapshot(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="snapshots")
    image = models.ImageField(upload_to="invigilation/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
