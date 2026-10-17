"""Confidential integrity & safeguarding reporting (public form + status check) and restricted case management."""
from django import forms
from django.contrib import messages
from django.core.cache import cache
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import STATE_CHOICES
from apps.accounts.roles import users_with_role
from apps.backoffice.decorators import staff_required
from apps.core.audit import client_ip
from apps.notifications.services import notify, send_email

from .models import CaseAccessLog, CaseNote, Report


class ReportForm(forms.ModelForm):
    anonymous = forms.BooleanField(required=False, initial=True, label="Report anonymously (we won't record who you are)")
    state = forms.ChoiceField(choices=[("", "Select…")] + STATE_CHOICES, required=False)

    class Meta:
        model = Report
        fields = ["category", "description", "people_involved", "sport", "state", "involves_child", "immediate_danger", "contact"]
        widgets = {"description": forms.Textarea(attrs={"rows": 6}), "people_involved": forms.Textarea(attrs={"rows": 2}),
                   "contact": forms.Textarea(attrs={"rows": 2})}
        labels = {"description": "What happened? Include when and where, if you can.",
                  "people_involved": "People involved (names or roles), optional",
                  "contact": "Safe way to contact you, optional (only seen by safeguarding officers)",
                  "involves_child": "A child (under 18) is involved", "immediate_danger": "Someone is in immediate danger"}


def report(request):
    form = ReportForm(request.POST or None)
    if request.method == "POST":
        key = f"integrity:{client_ip(request)}"
        if cache.get(key, 0) >= 10:
            messages.error(request, "Too many reports from this network. Please try again later or call the hotline.")
            return redirect("integrity:report")
        if form.is_valid():
            cache.set(key, cache.get(key, 0) + 1, 3600)
            r = form.save(commit=False)
            r.anonymous = form.cleaned_data["anonymous"]
            if not r.anonymous and request.user.is_authenticated:
                r.reporter = request.user
            r.save()
            for officer in users_with_role("safeguarding_officer"):
                notify(officer, f"New integrity report {r.reference}" + (" (URGENT)" if r.immediate_danger or r.involves_child else ""),
                       r.get_category_display(), f"/integrity/cases/{r.pk}/", sms=r.immediate_danger)
            return render(request, "integrity/thanks.html", {"r": r})
    return render(request, "integrity/report.html", {"form": form, "base": "app/base.html" if request.user.is_authenticated else "public/base.html"})


def status(request):
    r = None
    if request.method == "POST":
        r = Report.objects.filter(reference=request.POST.get("reference", "").strip().upper(),
                                  access_code=request.POST.get("code", "").strip()).first()
        if not r:
            messages.error(request, "No report matches that reference and access code.")
    return render(request, "integrity/status.html", {"r": r, "base": "app/base.html" if request.user.is_authenticated else "public/base.html"})


@staff_required("safeguarding_officer")
def cases(request):
    qs = Report.objects.all()
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    return render(request, "integrity/cases.html", {"cases": qs, "statuses": Report.STATUSES})


@staff_required("safeguarding_officer")
def case(request, pk):
    r = get_object_or_404(Report, pk=pk)
    CaseAccessLog.objects.create(report=r, user=request.user)
    if request.method == "POST":
        if request.POST.get("note", "").strip():
            CaseNote.objects.create(report=r, author=request.user, body=request.POST["note"][:10000], action=request.POST.get("status", ""))
        if request.POST.get("status") in dict(Report.STATUSES):
            r.status = request.POST["status"]
        if request.POST.get("assign"):
            r.assigned_to = users_with_role("safeguarding_officer").filter(pk=request.POST["assign"]).first()
        r.public_update = request.POST.get("public_update", r.public_update)[:255]
        r.save()
        messages.success(request, "Case updated.")
        return redirect("integrity:case", pk=pk)
    return render(request, "integrity/case.html", {
        "r": r, "notes": r.notes.select_related("author"), "statuses": Report.STATUSES,
        "officers": users_with_role("safeguarding_officer"),
        "access": r.access_log.select_related("user")[:20],
    })
