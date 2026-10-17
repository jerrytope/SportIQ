from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.notifications.services import notify

from .models import Attempt, Question, Response


class ExamUnavailable(Exception):
    pass


def start_attempt(exam, user):
    open_attempt = exam.attempts.filter(user=user, status=Attempt.IN_PROGRESS).first()
    if open_attempt:
        if open_attempt.is_open:
            return open_attempt
        submit_attempt(open_attempt, late=True)
    if not exam.is_open_now():
        raise ExamUnavailable("This assessment is not open right now. Check the scheduled window.")
    used = exam.attempts_for(user).count()
    if used >= exam.allowed_attempts(user):
        raise ExamUnavailable("You have used all permitted attempts. You can request a resit from the course page.")
    if exam.attempts.filter(user=user, passed=True).exists():
        raise ExamUnavailable("You have already passed this exam.")
    questions = exam.draw_questions()
    if not questions:
        raise ExamUnavailable("This exam has no questions yet.")
    with transaction.atomic():
        attempt = Attempt.objects.create(
            exam=exam, user=user, number=used + 1,
            deadline=timezone.now() + timedelta(minutes=exam.time_limit_minutes),
            max_score=sum(q.points for q in questions),
        )
        Response.objects.bulk_create(
            [Response(attempt=attempt, question=q, order=i) for i, q in enumerate(questions)]
        )
    return attempt


def save_answers(attempt, data):
    """`data` is a QueryDict from the exam form: q<id> → choice ids or text."""
    if attempt.status != Attempt.IN_PROGRESS:
        return
    for resp in attempt.responses.select_related("question"):
        key = f"q{resp.question_id}"
        q = resp.question
        if q.kind in (Question.MCQ, Question.TF, Question.MULTI):
            ids = [int(x) for x in data.getlist(key) if str(x).isdigit()]
            valid = list(q.choices.filter(pk__in=ids).values_list("pk", flat=True))
            if q.kind != Question.MULTI:
                valid = valid[:1]
            resp.selected.set(valid)
        elif key in data:
            resp.text = data.get(key, "")[:20000]
            resp.save(update_fields=["text"])


def auto_mark(resp):
    q = resp.question
    correct = set(q.choices.filter(is_correct=True).values_list("pk", flat=True))
    chosen = set(resp.selected.values_list("pk", flat=True))
    resp.score = Decimal(q.points) if chosen and chosen == correct else Decimal(0)
    resp.marked_at = timezone.now()
    resp.save(update_fields=["score", "marked_at"])


@transaction.atomic
def submit_attempt(attempt, late=False):
    if attempt.status != Attempt.IN_PROGRESS:
        return attempt
    attempt.submitted_at = timezone.now()
    if late:
        attempt.integrity_flags = list(attempt.integrity_flags) + ["auto-submitted at time limit"]
    for resp in attempt.responses.select_related("question"):
        if resp.question.is_auto_marked:
            auto_mark(resp)
    attempt.status = Attempt.SUBMITTED
    attempt.save()
    check_similarity(attempt)
    finalise_if_marked(attempt)
    return attempt


def _shingles(text, n=5):
    words = [w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w]
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def check_similarity(attempt, threshold=40):
    """Academic-integrity check: overlap (5-word shingles, Jaccard) of written answers with other learners' answers."""
    worst = 0.0
    for resp in attempt.responses.select_related("question"):
        if resp.question.is_auto_marked or len(resp.text.split()) < 25:
            continue
        mine = _shingles(resp.text)
        others = Response.objects.filter(question=resp.question).exclude(attempt__user=attempt.user).exclude(text="")
        for other in others.only("text")[:500]:
            theirs = _shingles(other.text)
            if mine and theirs:
                worst = max(worst, 100 * len(mine & theirs) / len(mine | theirs))
    attempt.similarity_flag = round(Decimal(worst), 1) if worst else None
    if worst >= threshold:
        attempt.integrity_flags = list(attempt.integrity_flags) + [f"{worst:.0f}% similar to another learner's answer"]
    attempt.save(update_fields=["similarity_flag", "integrity_flags"])
    return worst


def finalise_if_marked(attempt):
    responses = list(attempt.responses.select_related("question"))
    if any(r.score is None for r in responses):
        return False
    total = sum((r.score for r in responses), Decimal(0))
    attempt.score = total
    attempt.percent = round(Decimal(100) * total / attempt.max_score, 1) if attempt.max_score else Decimal(0)
    attempt.passed = attempt.percent >= attempt.exam.pass_mark
    attempt.status = Attempt.MARKED
    attempt.save()
    # Results with examiner-marked answers are released by a person (moderation step), never automatically.
    if attempt.exam.auto_release and not attempt.exam.requires_moderation and all(r.question.is_auto_marked for r in responses):
        release(attempt)
    return True


def mark_response(resp, score, feedback, marker, rubric_scores=None):
    score = max(Decimal(0), min(Decimal(str(score)), Decimal(resp.question.points)))
    resp.score = score
    resp.feedback = feedback
    resp.rubric_scores = rubric_scores or {}
    resp.marked_by = marker
    resp.marked_at = timezone.now()
    resp.save()
    finalise_if_marked(resp.attempt)


def release(attempt, actor=None):
    from apps.core.audit import audit

    if attempt.status != Attempt.MARKED:
        return
    if attempt.exam.requires_moderation and not attempt.moderated_by_id:
        raise ValueError("This exam requires moderation by a second marker before results are released.")
    attempt.status = Attempt.RELEASED
    attempt.released_at = timezone.now()
    attempt.save(update_fields=["status", "released_at"])
    audit(actor, "exam.result_released", attempt, {"percent": str(attempt.percent), "passed": attempt.passed})
    from apps.integrations.services import emit

    emit("exam.result_released", attempt.user, {"exam": attempt.exam.title, "course": attempt.exam.course.slug,
                                                 "percent": str(attempt.percent), "passed": attempt.passed})
    outcome = "passed" if attempt.passed else "did not pass"
    notify(attempt.user, f"Results released: {attempt.exam.title}",
           f"You scored {attempt.percent}% and {outcome}.", f"/learn/attempts/{attempt.pk}/")
    if attempt.passed:
        from apps.learning.models import Enrolment
        from apps.learning.services import award, check_completion

        award(attempt.user, "exam-pass")
        enrolment = Enrolment.objects.filter(user=attempt.user, course=attempt.exam.course).first()
        if enrolment:
            check_completion(enrolment)


def item_analysis(exam):
    """Facility (mean share of marks) and discrimination (upper 27% minus lower 27% facility) per question."""
    attempts = list(exam.attempts.filter(status__in=["marked", "released"], percent__isnull=False).order_by("-percent"))
    k = max(1, round(len(attempts) * 0.27))
    upper = {a.pk for a in attempts[:k]}
    lower = {a.pk for a in attempts[-k:]} if len(attempts) >= 2 else set()
    qs = Response.objects.filter(attempt__in=attempts, score__isnull=False).select_related("question")
    by_q = {}
    for r in qs:
        share = float(r.score) / max(r.question.points, 1)
        d = by_q.setdefault(r.question, {"all": [], "up": [], "low": []})
        d["all"].append(share)
        if r.attempt_id in upper:
            d["up"].append(share)
        if r.attempt_id in lower:
            d["low"].append(share)
    rows = []
    for q, d in by_q.items():
        mean = lambda xs: sum(xs) / len(xs) if xs else 0  # noqa: E731
        disc = round(mean(d["up"]) - mean(d["low"]), 2) if d["up"] and d["low"] else None
        rows.append({"question": q, "responses": len(d["all"]), "facility": round(100 * mean(d["all"])), "discrimination": disc})
    return sorted(rows, key=lambda r: r["facility"])
