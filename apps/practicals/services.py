from django.utils import timezone

from apps.core.audit import audit
from apps.notifications.services import notify, send_email


def submit(task, user, text="", file=None, video=None, video_url="", supervisor=None, request=None):
    from .models import Submission

    attempt = Submission.objects.filter(task=task, user=user).count() + 1
    sub = Submission.objects.create(task=task, user=user, text=text, file=file or "", video=video or "",
                                    video_url=video_url, attempt=attempt, **(supervisor or {}))
    if task.requires_supervisor and sub.supervisor_email:
        link = (request.build_absolute_uri(sub.signoff_url()) if request else sub.signoff_url())
        send_email(sub.supervisor_email, f"SportIQ: please confirm {user.get_full_name()}'s practical competence",
                   f"Hello {sub.supervisor_name},\n\n{user.get_full_name()} has named you as the supervisor who observed "
                   f"'{task.title}' ({task.course.title}).\n\nPlease review and confirm (or decline) here:\n{link}\n\n"
                   "Only confirm if you personally observed the learner demonstrate this competence.")
    for instructor in task.course.instructors.all():
        notify(instructor, f"Practical submitted: {task.title}", str(user), "/manage/practicals/", email=False)
    return sub


def assess(sub, scores, feedback, assessor, outcome=None):
    """Score against the rubric. Pass requires the pass mark AND (if needed) supervisor sign-off."""
    total = sub.task.rubric_total
    got = sum(min(int(scores.get(str(i), 0) or 0), int(c.get("max", 0))) for i, c in enumerate(sub.task.rubric))
    pct = round(100 * got / total) if total else 0
    sub.rubric_scores = scores
    sub.score_percent = pct
    sub.feedback = feedback
    sub.assessed_by = assessor
    sub.assessed_at = timezone.now()
    if outcome == "revise":
        sub.status = "revise"
    else:
        sub.status = "passed" if pct >= sub.task.pass_mark else "failed"
    sub.save()
    audit(assessor, f"practical.{sub.status}", sub, {"percent": pct})
    msg = {"passed": "assessed as competent", "failed": "not yet competent", "revise": "needs revision"}[sub.status]
    if sub.status == "passed" and sub.awaiting_supervisor:
        msg += " (waiting for your supervisor's sign-off)"
    notify(sub.user, f"Practical {msg}: {sub.task.title}", feedback[:300], f"/practicals/submissions/{sub.pk}/")
    after_change(sub)
    return sub


def is_complete(sub):
    return sub.status == "passed" and not sub.awaiting_supervisor


def after_change(sub):
    """When a practical becomes complete, tick the linked lesson and re-check qualifications."""
    if not is_complete(sub):
        return
    from apps.credentials.services import check_programmes, record_cpd
    from apps.learning import services as learning
    from apps.learning.models import Enrolment

    record_cpd(sub.user, f"Practical: {sub.task.title}", "practice", 2, f"practical:{sub.task_id}")
    enrolment = Enrolment.objects.filter(user=sub.user, course=sub.task.course).first()
    if enrolment:
        for lesson in sub.task.lessons.all():
            learning.complete_lesson(enrolment, lesson)
    check_programmes(sub.user)


def supervisor_decision(sub, confirm, comment):
    if confirm:
        sub.supervisor_signed_at = timezone.now()
    sub.supervisor_comment = comment
    sub.save(update_fields=["supervisor_signed_at", "supervisor_comment"])
    audit(None, "practical.supervisor_" + ("confirmed" if confirm else "declined"), sub,
          {"supervisor": sub.supervisor_email})
    notify(sub.user, f"Supervisor {'confirmed' if confirm else 'did not confirm'}: {sub.task.title}", comment[:300],
           f"/practicals/submissions/{sub.pk}/")
    after_change(sub)
