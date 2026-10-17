from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.learning.models import Enrolment

from . import services
from .models import PracticalTask, Submission


class SubmissionForm(forms.Form):
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}), required=False, label="Your submission",
                           help_text="Paste your plan/report, or upload a file below.")
    file = forms.FileField(required=False, label="Document (PDF, Word, spreadsheet)")
    video = forms.FileField(required=False, label="Video evidence (max 200 MB)")
    video_url = forms.URLField(required=False, label="…or link to an unlisted video")
    supervisor_name = forms.CharField(required=False, max_length=120)
    supervisor_email = forms.EmailField(required=False)
    supervisor_role = forms.CharField(required=False, max_length=120, label="Supervisor's role / qualification")

    def __init__(self, *a, task=None, **kw):
        super().__init__(*a, **kw)
        self.task = task
        if not task.accepts_video:
            del self.fields["video"], self.fields["video_url"]
        if not task.requires_supervisor:
            for f in ("supervisor_name", "supervisor_email", "supervisor_role"):
                del self.fields[f]
        else:
            for f in ("supervisor_name", "supervisor_email", "supervisor_role"):
                self.fields[f].required = True

    def clean(self):
        d = super().clean()
        if not (d.get("text") or d.get("file") or d.get("video") or d.get("video_url")):
            raise forms.ValidationError("Add your work as text, a file or a video.")
        f = d.get("video")
        if f and f.size > 200 * 1024 * 1024:
            self.add_error("video", "Video is larger than 200 MB. Upload a link instead.")
        return d


@login_required
def task_view(request, pk):
    task = get_object_or_404(PracticalTask.objects.select_related("course"), pk=pk)
    if not Enrolment.objects.filter(user=request.user, course=task.course).exists():
        messages.error(request, "Enrol in the course to submit this practical.")
        return redirect(task.course)
    subs = task.submissions.filter(user=request.user)
    latest = subs.first()
    can_submit = not latest or latest.status in ("revise", "failed")
    form = SubmissionForm(request.POST or None, request.FILES or None, task=task)
    if request.method == "POST" and can_submit and form.is_valid():
        d = form.cleaned_data
        sup = {k: d[k] for k in ("supervisor_name", "supervisor_email", "supervisor_role") if k in d}
        sub = services.submit(task, request.user, d.get("text", ""), d.get("file"), d.get("video"), d.get("video_url", ""),
                              sup, request)
        messages.success(request, "Submitted. An assessor will review it" +
                         (" and we've emailed your supervisor to confirm." if task.requires_supervisor else "."))
        return redirect("practicals:submission", pk=sub.pk)
    return render(request, "practicals/task.html", {"task": task, "form": form, "submissions": subs, "can_submit": can_submit})


@login_required
def submission(request, pk):
    sub = get_object_or_404(Submission.objects.select_related("task__course"), pk=pk)
    if sub.user != request.user and not request.user.has_role("instructor", "academic_manager"):
        raise Http404
    return render(request, "practicals/submission.html", {"sub": sub, "criteria": [
        {"title": c.get("title"), "max": c.get("max"), "score": sub.rubric_scores.get(str(i))} for i, c in enumerate(sub.task.rubric)]})


def signoff(request, token):
    """Public page for an external supervisor (no account needed) to confirm observed competence."""
    sub = get_object_or_404(Submission.objects.select_related("task__course", "user"), supervisor_token=token)
    if request.method == "POST" and not sub.supervisor_signed_at:
        confirm = request.POST.get("decision") == "confirm"
        if confirm and request.POST.get("declare") != "on":
            messages.error(request, "Please tick the declaration to confirm.")
        else:
            services.supervisor_decision(sub, confirm, request.POST.get("comment", "")[:2000])
            messages.success(request, "Thank you, your response has been recorded.")
            return redirect("practicals:signoff", token=token)
    return render(request, "practicals/signoff.html", {"sub": sub})
