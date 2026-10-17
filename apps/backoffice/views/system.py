from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import DataRequest
from apps.commerce import services as commerce
from apps.core.audit import audit
from apps.core.models import AuditLog, SiteSettings, add_months
from apps.credentials import services as cred_services
from apps.credentials.models import Credential, CredentialType, VerificationLog
from apps.notifications.services import notify

from ..decorators import staff_required
from ..forms import CredentialTypeForm, IssueCredentialForm, PlatformSettingsForm


@staff_required("registrar")
def credentials(request):
    qs = Credential.objects.select_related("user", "credential_type")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(user__email__icontains=q) | Q(holder_name__icontains=q) | Q(title__icontains=q))
    status = request.GET.get("status")
    if status == "expiring":
        qs = qs.filter(status="active", expires_at__gte=timezone.now(), expires_at__lte=timezone.now() + timezone.timedelta(days=60))
    elif status:
        qs = qs.filter(status=status)
    type_form = CredentialTypeForm(request.POST if request.POST.get("form") == "type" else None)
    if request.method == "POST" and request.POST.get("form") == "type" and type_form.is_valid():
        ct = type_form.save()
        audit(request.user, "credential_type.created", ct, request=request)
        messages.success(request, f"Credential type “{ct.name}” created.")
        return redirect("backoffice:credentials")
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "manage/credentials/list.html", {
        "page": page, "q": q, "status": status, "types": CredentialType.objects.all(), "type_form": type_form,
        "recent_checks": VerificationLog.objects.select_related("credential")[:10],
    })


@staff_required("registrar")
def credential_issue(request):
    form = IssueCredentialForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        cred = cred_services.issue(d["user"], d["credential_type"], d["title"], course=d.get("course"),
                                   actor=request.user, grade=d.get("grade", ""))
        messages.success(request, f"Issued {cred.code} to {cred.holder_name}.")
        return redirect("backoffice:credential_manage", pk=cred.pk)
    return render(request, "manage/simple_form.html", {
        "form": form, "title": "Issue a credential manually", "back_url": "backoffice:credentials",
        "help": "Use this for qualifications assessed outside the platform (for example a supervised practical). "
                "Course completion certificates are issued automatically.",
    })


@staff_required("registrar")
def credential_manage(request, pk):
    cred = get_object_or_404(Credential.objects.select_related("user", "credential_type", "course"), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        reason = request.POST.get("reason", "").strip()
        if action in ("suspended", "revoked", "active"):
            if action != "active" and not reason:
                messages.error(request, "A reason is required. It is recorded in the audit trail.")
            else:
                cred_services.change_status(cred, action, reason, request.user, request)
                messages.success(request, "Status updated.")
        elif action == "correct":
            new_name = request.POST.get("holder_name", "").strip()
            if new_name and new_name != cred.holder_name:
                old = cred.holder_name
                cred.holder_name = new_name
                cred.save(update_fields=["holder_name"])
                cred.events.create(action="corrected", note=f"Name: {old} → {new_name}. {reason}", actor=request.user)
                audit(request.user, "credential.corrected", cred, {"from": old, "to": new_name}, request)
                messages.success(request, "Name corrected.")
        elif action == "renew" and cred.credential_type.validity_months:
            cred.expires_at = add_months(max(cred.expires_at or timezone.now(), timezone.now()), cred.credential_type.validity_months)
            cred.save(update_fields=["expires_at"])
            cred.events.create(action="renewed", note=reason, actor=request.user)
            audit(request.user, "credential.renewed", cred, {"expires": cred.expires_at.isoformat()}, request)
            notify(cred.user, f"Credential renewed: {cred.title}", f"New expiry {cred.expires_at:%d %b %Y}.", cred.get_absolute_url())
            messages.success(request, "Credential renewed.")
        return redirect("backoffice:credential_manage", pk=pk)
    return render(request, "manage/credentials/detail.html", {"cred": cred, "events": cred.events.select_related("actor"),
                                                              "checks": cred.verifications.all()[:20]})


@staff_required("super_admin")
def settings_view(request):
    form = PlatformSettingsForm(request.POST or None, instance=SiteSettings.load())
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request.user, "settings.updated", None, {"fields": form.changed_data}, request)
        messages.success(request, "Settings saved.")
        return redirect("backoffice:settings")
    from django.conf import settings as dj

    integrations = [
        ("Paystack payments", commerce.live_mode(), "PAYSTACK_SECRET_KEY"),
        ("Termii SMS", bool(dj.TERMII_API_KEY), "TERMII_API_KEY"),
        ("Email (SMTP)", "smtp" in dj.EMAIL_BACKEND, "EMAIL_BACKEND / EMAIL_HOST"),
        ("Background jobs (Celery)", bool(dj.CELERY_BROKER_URL), "CELERY_BROKER_URL"),
        ("Staff two-factor enforced", dj.REQUIRE_STAFF_2FA, "REQUIRE_STAFF_2FA"),
    ]
    return render(request, "manage/settings.html", {"form": form, "integrations": integrations})


@staff_required("super_admin")
def audit_log(request):
    qs = AuditLog.objects.select_related("actor")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(action__icontains=q) | Q(object_repr__icontains=q) | Q(actor__email__icontains=q))
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "manage/audit.html", {"page": page, "q": q})


@staff_required("super_admin")
def data_requests(request):
    if request.method == "POST":
        dr = get_object_or_404(DataRequest, pk=request.POST.get("request"))
        dr.status = request.POST.get("status", "done")
        dr.resolution_note = request.POST.get("note", "")
        dr.resolved_at = timezone.now()
        dr.save()
        if dr.kind == "delete" and dr.status == "done":
            u = dr.user
            u.is_active = False
            u.first_name, u.last_name, u.phone, u.bio, u.lga = "Deleted", "user", "", "", ""
            u.has_disability, u.accessibility_needs = None, ""
            u.email = f"deleted-{u.pk}@deleted.sportiq.invalid"
            u.deactivated_reason = "Deleted at user request (NDPA)"
            u.save()
            # Credentials are kept as an institutional record but the holder can no longer sign in.
        audit(request.user, f"privacy.request_{dr.status}", dr, {"kind": dr.kind, "note": dr.resolution_note}, request)
        messages.success(request, "Request updated.")
        return redirect("backoffice:data_requests")
    return render(request, "manage/data_requests.html", {"requests": DataRequest.objects.select_related("user")})
