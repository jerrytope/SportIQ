import base64
import io
import json
import zipfile

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.core.audit import audit, client_ip
from apps.notifications.services import send_email

from .forms import LoginForm, PreferencesForm, ProfileForm, SensitiveDataForm, SignupForm, TokenForm
from .models import Consent, DataRequest

VERIFY_SALT = "sportiq.email-verify"
MAX_FAILURES = 8


def _lockout_key(request, email):
    """Failed-login counter per IP and email. A password reset bumps the email's generation, clearing every lock."""
    email = (email or "").lower()
    return f"login-fail:{cache.get(f'login-gen:{email}', 0)}:{client_ip(request)}:{email}"


def clear_lockout(email):
    key = f"login-gen:{(email or '').lower()}"
    cache.set(key, cache.get(key, 0) + 1, None)


def _safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}):
        return nxt
    return default


def send_verification(request, user):
    token = signing.dumps({"u": user.pk}, salt=VERIFY_SALT)
    url = request.build_absolute_uri(reverse("accounts:verify_email", args=[token]))
    send_email(user.email, "Confirm your SportIQ email",
               f"Hello {user.first_name},\n\nConfirm your email address to secure your account:\n{url}\n\n"
               "This link expires in 3 days.")


def signup(request):
    if request.user.is_authenticated:
        return redirect("learning:dashboard")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        Consent.objects.create(user=user, kind="terms")
        Consent.objects.create(user=user, kind="privacy")
        if form.cleaned_data.get("marketing"):
            Consent.objects.create(user=user, kind="marketing")
        send_verification(request, user)
        login(request, user, backend="apps.accounts.backends.EmailBackend")
        audit(user, "account.signup", user, request=request)
        messages.success(request, f"Welcome to SportIQ, {user.first_name}! We've sent a link to confirm your email.")
        return redirect(_safe_next(request, reverse("learning:dashboard")))
    return render(request, "accounts/signup.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def _key(self):
        return _lockout_key(self.request, self.request.POST.get("username"))

    def post(self, request, *args, **kwargs):
        if cache.get(self._key(), 0) >= MAX_FAILURES:
            messages.error(request, "Too many failed attempts. Please wait 15 minutes or reset your password.")
            return redirect("accounts:login")
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._key()
        cache.set(key, cache.get(key, 0) + 1, 15 * 60)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._key())
        response = super().form_valid(form)
        audit(self.request.user, "account.login", self.request.user, request=self.request)
        return response

    def get_default_redirect_url(self):
        user = self.request.user
        if user.is_backoffice and not user.enrolments.exists():
            return reverse("backoffice:home")
        return reverse("learning:dashboard")


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("web:home")


def verify_email(request, token):
    from .models import User

    try:
        data = signing.loads(token, salt=VERIFY_SALT, max_age=3 * 24 * 3600)
        user = User.objects.get(pk=data["u"])
    except (signing.BadSignature, User.DoesNotExist):
        messages.error(request, "That confirmation link is invalid or has expired.")
        return redirect("web:home")
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    messages.success(request, "Your email address is confirmed.")
    return redirect("learning:dashboard" if request.user.is_authenticated else "accounts:login")


@login_required
@require_POST
def resend_verification(request):
    send_verification(request, request.user)
    messages.success(request, "We've sent a new confirmation link.")
    return redirect(request.META.get("HTTP_REFERER") or "learning:dashboard")


@login_required
def profile(request):
    user = request.user
    form = ProfileForm(request.POST or None, request.FILES or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {
        "form": form,
        "credentials": user.credentials.select_related("credential_type")[:6],
        "memberships": user.memberships.select_related("institution"),
        "completed": user.enrolments.filter(status="completed").select_related("course"),
    })


@login_required
def settings_view(request):
    user = request.user
    prefs = PreferencesForm(request.POST if "save_prefs" in request.POST else None, instance=user, prefix="p")
    pwd = PasswordChangeForm(user, request.POST if "change_password" in request.POST else None, prefix="pw")
    sensitive = SensitiveDataForm(request.POST if "save_sensitive" in request.POST else None, instance=user, prefix="s")
    if request.method == "POST":
        if "save_prefs" in request.POST and prefs.is_valid():
            prefs.save()
            messages.success(request, "Preferences saved.")
            return redirect("accounts:settings")
        if "change_password" in request.POST and pwd.is_valid():
            pwd.save()
            update_session_auth_hash(request, pwd.user)
            audit(user, "account.password_changed", user, request=request)
            messages.success(request, "Password changed.")
            return redirect("accounts:settings")
        if "save_sensitive" in request.POST and sensitive.is_valid():
            if sensitive.cleaned_data["consent"]:
                sensitive.save()
                Consent.objects.create(user=user, kind="sensitive", granted=True)
                messages.success(request, "Saved. Thank you, this helps us improve inclusion.")
            else:
                user.has_disability = None
                user.accessibility_needs = ""
                user.save(update_fields=["has_disability", "accessibility_needs"])
                Consent.objects.create(user=user, kind="sensitive", granted=False)
                messages.info(request, "Consent withdrawn and sensitive data removed.")
            return redirect("accounts:settings")
    has_2fa = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
    return render(request, "accounts/settings.html", {
        "prefs": prefs, "pwd": pwd, "sensitive": sensitive, "has_2fa": has_2fa,
        "consents": user.consents.all()[:10], "data_requests": user.data_requests.all(),
    })


@login_required
@require_POST
def data_request(request):
    kind = request.POST.get("kind")
    if kind not in dict(DataRequest.KINDS):
        return redirect("accounts:settings")
    DataRequest.objects.create(user=request.user, kind=kind, details=request.POST.get("details", "")[:2000])
    audit(request.user, f"privacy.request_{kind}", request.user, request=request)
    messages.success(request, "Your request has been logged. We will respond within 30 days as required by the NDPA.")
    return redirect("accounts:settings")


@login_required
def export_data(request):
    """Immediate self-service export of the learner's own data (JSON in a ZIP)."""
    u = request.user
    data = {
        "profile": {"name": u.get_full_name(), "email": u.email, "phone": u.phone, "state": u.state, "lga": u.lga,
                    "gender": u.gender, "languages": u.languages, "bio": u.bio,
                    "professions": [p.name for p in u.professions.all()], "sports": [s.name for s in u.sports.all()],
                    "joined": u.date_joined.isoformat()},
        "enrolments": [{"course": e.course.title, "status": e.status, "progress": e.progress,
                        "enrolled": e.created_at.isoformat(),
                        "completed": e.completed_at.isoformat() if e.completed_at else None}
                       for e in u.enrolments.select_related("course")],
        "exam_attempts": [{"exam": a.exam.title, "number": a.number, "percent": str(a.percent), "passed": a.passed,
                           "submitted": a.submitted_at.isoformat() if a.submitted_at else None}
                          for a in u.attempts.select_related("exam")],
        "credentials": [{"title": c.title, "code": c.code, "type": c.credential_type.name, "status": c.status,
                         "issued": c.issued_at.isoformat()} for c in u.credentials.select_related("credential_type")],
        "orders": [{"reference": o.reference, "course": o.course.title, "amount_naira": o.amount_naira,
                    "status": o.status} for o in u.orders.select_related("course")],
        "consents": [{"kind": c.kind, "granted": c.granted, "at": c.created_at.isoformat()} for c in u.consents.all()],
        "notes": [{"lesson": n.lesson.title, "note": n.body} for n in u.notes.select_related("lesson")],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("sportiq-my-data.json", json.dumps(data, indent=2))
    audit(u, "privacy.export_downloaded", u, request=request)
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="sportiq-data-{timezone.localdate()}.zip"'
    return resp


@login_required
def payments(request):
    return render(request, "accounts/payments.html", {"orders": request.user.orders.select_related("course")})


# --- Two-factor (TOTP) ---------------------------------------------------------------

def _qr_data_uri(text):
    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@login_required
def two_factor_setup(request):
    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
    if not device:
        device = TOTPDevice.objects.create(user=request.user, name="Authenticator app", confirmed=False)
    form = TokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if device.verify_token(form.cleaned_data["token"]):
            device.confirmed = True
            device.save()
            TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()
            otp_login(request, device)
            audit(request.user, "account.2fa_enabled", request.user, request=request)
            messages.success(request, "Two-factor authentication is on.")
            return redirect(_safe_next(request, reverse("accounts:settings")))
        form.add_error("token", "That code is not correct. Check your phone's clock and try again.")
    secret = base64.b32encode(device.bin_key).decode()
    return render(request, "accounts/two_factor_setup.html", {
        "form": form, "qr": _qr_data_uri(device.config_url), "secret": secret,
        "next": request.GET.get("next", ""),
    })


@login_required
def two_factor_verify(request):
    form = TokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        for device in TOTPDevice.objects.filter(user=request.user, confirmed=True):
            if device.verify_token(form.cleaned_data["token"]):
                otp_login(request, device)
                default = "backoffice:home" if request.user.is_backoffice else "learning:dashboard"
                return redirect(_safe_next(request, reverse(default)))
        form.add_error("token", "That code is not correct.")
    return render(request, "accounts/two_factor_verify.html", {"form": form, "next": request.GET.get("next", "")})


@login_required
@require_POST
def two_factor_disable(request):
    if request.user.is_backoffice and settings.REQUIRE_STAFF_2FA:
        messages.error(request, "Staff accounts must keep two-factor authentication switched on.")
        return redirect("accounts:settings")
    TOTPDevice.objects.filter(user=request.user).delete()
    audit(request.user, "account.2fa_disabled", request.user, request=request)
    messages.info(request, "Two-factor authentication is off.")
    return redirect("accounts:settings")


password_reset = auth_views.PasswordResetView.as_view(
    template_name="accounts/password_reset.html", email_template_name="accounts/email_password_reset.txt",
    subject_template_name="accounts/email_password_reset_subject.txt",
    success_url=reverse_lazy("accounts:password_reset_done"))
password_reset_done = auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html")
class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        clear_lockout(form.user.email)  # the lockout message promises that a reset lets you back in
        return super().form_valid(form)


password_reset_confirm = PasswordResetConfirmView.as_view()
password_reset_complete = auth_views.PasswordResetCompleteView.as_view(
    template_name="accounts/password_reset_complete.html")
