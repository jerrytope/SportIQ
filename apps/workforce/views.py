from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import NIGERIAN_STATES, Consent, User
from apps.careers.models import LEVELS
from apps.catalog.models import Profession, Sport
from apps.core.audit import audit
from apps.credentials.models import CredentialType
from apps.notifications.services import notify

from . import services
from .models import ContactRequest, DirectorySearch, WorkforceProfile


class ListingForm(forms.ModelForm):
    preferred_states = forms.MultipleChoiceField(choices=[(s, s) for s in NIGERIAN_STATES], required=False,
                                                 widget=forms.SelectMultiple(attrs={"size": 6}), label="States where you can work")
    experience_levels = forms.MultipleChoiceField(choices=LEVELS, required=False, widget=forms.CheckboxSelectMultiple,
                                                  label="Experience in")

    class Meta:
        model = WorkforceProfile
        fields = ["listed", "availability", "preferred_states", "willing_to_relocate", "experience_levels", "specialisations", "years_experience"]
        labels = {"listed": "List me in the national sports workforce directory (authorised NIS, federation, state council and employer searches only)"}


@login_required
def my_listing(request):
    profile, _ = WorkforceProfile.objects.get_or_create(user=request.user)
    form = ListingForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        was = profile.listed
        form.save()
        if form.cleaned_data["listed"] != was:
            Consent.objects.create(user=request.user, kind="directory", granted=form.cleaned_data["listed"])
        messages.success(request, "Directory preferences saved.")
        return redirect("workforce:my_listing")
    return render(request, "workforce/my_listing.html", {
        "form": form, "requests": request.user.contact_requests.select_related("requester", "institution")})


@login_required
@require_POST
def respond(request, pk):
    r = get_object_or_404(ContactRequest, pk=pk, professional=request.user, status="pending")
    r.status = "accepted" if request.POST.get("accept") else "declined"
    r.save()
    if r.status == "accepted":
        notify(r.requester, f"{request.user} accepted your contact request",
               f"Email: {request.user.email}" + (f" · Phone: {request.user.phone}" if request.user.phone else ""), "/workforce/")
    return redirect("workforce:my_listing")


@login_required
def search(request):
    if not services.can_search(request.user):
        return render(request, "workforce/not_authorised.html", status=403)
    keys = ("profession", "sport", "state", "credential", "level", "available", "verified")
    filters = {k: request.GET.get(k) for k in keys if request.GET.get(k)}
    results = page = None
    if filters:
        results = services.directory(filters)
        inst = request.user.memberships.filter(role="admin").select_related("institution").first()
        DirectorySearch.objects.create(searched_by=request.user, institution=inst.institution if inst else None, filters=filters, results=results.count())
        page = Paginator(results, 20).get_page(request.GET.get("page"))
    return render(request, "workforce/search.html", {
        "page": page, "filters": filters, "professions": Profession.objects.all(), "sports": Sport.objects.all(),
        "states": NIGERIAN_STATES, "credential_types": CredentialType.objects.all(), "levels": LEVELS, "searched": bool(filters),
    })


@login_required
@require_POST
def contact(request, user_id):
    if not services.can_search(request.user):
        raise Http404
    person = get_object_or_404(User, pk=user_id, workforce_profile__listed=True)
    inst = request.user.memberships.filter(role="admin").select_related("institution").first()
    ContactRequest.objects.create(professional=person, requester=request.user, institution=inst.institution if inst else None,
                                  message=request.POST.get("message", "")[:2000])
    audit(request.user, "workforce.contact_requested", person, request=request)
    notify(person, "An organisation would like to contact you", request.POST.get("message", "")[:300], "/workforce/me/")
    messages.success(request, "Request sent. They'll share contact details if they accept.")
    return redirect(request.META.get("HTTP_REFERER") or "workforce:search")


@login_required
def skills_map(request):
    if not (services.can_search(request.user) or request.user.has_role("analyst")):
        return render(request, "workforce/not_authorised.html", status=403)
    cells, gaps, total, qualified = services.skills_map(request.GET.get("profession"), request.GET.get("sport"), request.GET.get("credential"))
    return render(request, "workforce/skills_map.html", {
        "cells": cells, "gaps": gaps, "total": total, "qualified": qualified, "professions": Profession.objects.all(),
        "sports": Sport.objects.all(), "credential_types": CredentialType.objects.all(), "suppress": services.SUPPRESS_BELOW,
    })
