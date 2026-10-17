import base64
import json
import secrets
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation

import jwt
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.catalog.models import Lesson
from apps.core.audit import audit
from apps.learning.models import Enrolment

from . import lti, scorm
from .models import ApiKey, ExternalIdentity, LtiPlatform, ScormAttempt, XAPIStatement


# --- SCORM player ------------------------------------------------------------------------------

@login_required
@xframe_options_sameorigin
def scorm_launch(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related("scorm", "module__course"), pk=lesson_id, kind="scorm")
    if not Enrolment.objects.filter(user=request.user, course=lesson.module.course).exists() and not request.user.is_backoffice:
        raise Http404
    pkg = lesson.scorm
    att, _ = ScormAttempt.objects.get_or_create(package=pkg, user=request.user)
    return render(request, "integrations/scorm_player.html", {
        "pkg": pkg, "lesson": lesson, "cmi": json.dumps(att.cmi),
        "content_url": f"{settings.MEDIA_URL}{pkg.extracted_dir}/{pkg.launch_path}",
        "commit_url": reverse("integrations:scorm_commit", args=[lesson.pk]),
        "learner_id": request.user.pk, "learner_name": f"{request.user.last_name}, {request.user.first_name}",
    })


@login_required
@require_POST
def scorm_commit(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related("scorm", "module__course"), pk=lesson_id, kind="scorm")
    att = get_object_or_404(ScormAttempt, package=lesson.scorm, user=request.user)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return HttpResponseBadRequest()
    att.cmi.update({k: str(v)[:4096] for k, v in data.items() if isinstance(k, str) and k.startswith("cmi.")})
    raw = att.cmi.get("cmi.core.score.raw") or att.cmi.get("cmi.score.raw")
    try:
        att.score = Decimal(raw) if raw not in (None, "") else att.score
    except InvalidOperation:
        pass
    if not att.completed and scorm.is_complete(att.cmi, lesson.scorm.version):
        att.completed = True
        enrolment = Enrolment.objects.filter(user=request.user, course=lesson.module.course).first()
        if enrolment:
            from apps.learning.services import complete_lesson

            complete_lesson(enrolment, lesson)
        XAPIStatement.objects.create(statement_id=uuid.uuid4(), user=request.user, source="scorm",
                                     actor={"mbox": f"mailto:{request.user.email}"},
                                     verb="http://adlnet.gov/expapi/verbs/completed",
                                     object_id=request.build_absolute_uri(lesson.get_absolute_url()),
                                     result={"score": {"raw": str(att.score)} if att.score is not None else {}},
                                     raw={"verb": "completed", "scorm": True})
    att.save()
    return JsonResponse({"ok": True, "completed": att.completed})


# --- API key auth helper + xAPI Learning Record Store -------------------------------------------

def api_key_from(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    raw = ""
    if header.startswith("Bearer "):
        raw = header[7:].strip()
    elif header.startswith("Basic "):
        try:
            user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
            raw = pw or user
        except (ValueError, UnicodeDecodeError):
            raw = ""
    if not raw or "." not in raw:
        return None
    key = ApiKey.objects.filter(prefix=raw.split(".")[0], is_active=True).first()
    if key and secrets.compare_digest(key.key_hash, ApiKey.hash(raw)):
        ApiKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return key
    return None


@csrf_exempt
def xapi_statements(request):
    key = api_key_from(request)
    if request.method == "POST":
        if not (key and "xapi:write" in key.scopes) and not request.user.is_authenticated:
            return JsonResponse({"error": "unauthorised"}, status=401)
        try:
            payload = json.loads(request.body)
        except ValueError:
            return HttpResponseBadRequest("invalid JSON")
        statements = payload if isinstance(payload, list) else [payload]
        ids = []
        for st in statements[:100]:
            if not isinstance(st, dict) or "actor" not in st or "verb" not in st or "object" not in st:
                return HttpResponseBadRequest("statement must contain actor, verb and object")
            sid = st.get("id") or str(uuid.uuid4())
            mbox = str(st["actor"].get("mbox", "")).replace("mailto:", "")
            user = User.objects.filter(email__iexact=mbox).first() if mbox else None
            XAPIStatement.objects.update_or_create(statement_id=sid, defaults={
                "user": user, "actor": st["actor"], "verb": str(st["verb"].get("id", ""))[:255],
                "object_id": str(st["object"].get("id", ""))[:500], "result": st.get("result"), "raw": st,
                "source": key.name if key else "session"})
            ids.append(sid)
        return JsonResponse(ids, safe=False)
    if request.method == "GET":
        if not (key and "xapi:read" in key.scopes) and not (request.user.is_authenticated and request.user.has_role("analyst")):
            return JsonResponse({"error": "unauthorised"}, status=401)
        qs = XAPIStatement.objects.all()
        if request.GET.get("verb"):
            qs = qs.filter(verb=request.GET["verb"])
        if request.GET.get("activity"):
            qs = qs.filter(object_id=request.GET["activity"])
        return JsonResponse({"statements": [s.raw for s in qs[:200]], "more": ""})
    return HttpResponse(status=405)


# --- Institution-scoped API (API key) ------------------------------------------------------------

def _scoped(request, scope):
    key = api_key_from(request)
    if not key or scope not in key.scopes:
        return None, JsonResponse({"error": "invalid key or missing scope", "scope": scope}, status=401)
    return key, None


def api_members_credentials(request):
    key, err = _scoped(request, "credentials:read")
    if err:
        return err
    if not key.institution_id:
        return JsonResponse({"error": "key is not linked to an institution"}, status=403)
    from apps.credentials.models import Credential

    creds = Credential.objects.filter(user__memberships__institution=key.institution).select_related("credential_type", "user")
    return JsonResponse({"institution": key.institution.name, "credentials": [
        {"holder": c.holder_name, "email": c.user.email, "code": c.code, "title": c.title, "kind": c.credential_type.kind,
         "status": c.effective_status, "issued_at": c.issued_at.isoformat(),
         "expires_at": c.expires_at.isoformat() if c.expires_at else None} for c in creds.distinct()[:1000]]})


def api_members_enrolments(request):
    key, err = _scoped(request, "enrolments:read")
    if err:
        return err
    if not key.institution_id:
        return JsonResponse({"error": "key is not linked to an institution"}, status=403)
    qs = Enrolment.objects.filter(user__memberships__institution=key.institution).select_related("user", "course").distinct()
    return JsonResponse({"institution": key.institution.name, "enrolments": [
        {"email": e.user.email, "name": e.user.get_full_name(), "course": e.course.slug, "status": e.status,
         "progress": e.progress, "completed_at": e.completed_at.isoformat() if e.completed_at else None} for e in qs[:2000]]})


# --- LTI 1.3 tool --------------------------------------------------------------------------------

@csrf_exempt
def lti_login(request):
    """OIDC third-party login initiation from an LMS."""
    params = request.POST if request.method == "POST" else request.GET
    platform = LtiPlatform.objects.filter(issuer=params.get("iss"), client_id=params.get("client_id", ""), is_active=True).first() \
        or LtiPlatform.objects.filter(issuer=params.get("iss"), is_active=True).first()
    if not platform:
        return HttpResponseBadRequest("Unknown LTI platform")
    state, nonce = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    request.session["lti_state"], request.session["lti_nonce"] = state, nonce
    request.session["lti_platform"] = platform.pk
    query = urllib.parse.urlencode({
        "scope": "openid", "response_type": "id_token", "response_mode": "form_post", "prompt": "none",
        "client_id": platform.client_id, "redirect_uri": request.build_absolute_uri(reverse("integrations:lti_launch")),
        "login_hint": params.get("login_hint", ""), "lti_message_hint": params.get("lti_message_hint", ""),
        "state": state, "nonce": nonce})
    return redirect(f"{platform.auth_login_url}?{query}")


@csrf_exempt
@require_POST
def lti_launch(request):
    if request.POST.get("state") != request.session.get("lti_state"):
        return HttpResponseBadRequest("State mismatch")
    platform = get_object_or_404(LtiPlatform, pk=request.session.get("lti_platform"))
    try:
        claims = lti.decode_launch(request.POST.get("id_token", ""), platform, request.session.get("lti_nonce"))
    except Exception as exc:  # noqa: BLE001 - any validation failure rejects the launch
        audit(None, "lti.launch_rejected", platform, {"error": str(exc)[:200]}, request)
        return HttpResponseBadRequest("Invalid LTI launch")
    user = lti.user_for(claims, platform)
    login(request, user, backend="apps.accounts.backends.EmailBackend")
    audit(user, "lti.launch", platform, {"context": claims.get("https://purl.imsglobal.org/spec/lti/claim/context", {}).get("title", "")}, request)
    target = lti.target_url(claims) or reverse("learning:dashboard")
    return redirect(target)


def lti_jwks(request):
    return JsonResponse(lti.public_jwks())


# --- OpenID Connect single sign-on ------------------------------------------------------------------

def _oidc_config():
    if not (settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID):
        raise Http404
    with urllib.request.urlopen(settings.OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration", timeout=10) as r:
        return json.loads(r.read())


def sso_start(request):
    conf = _oidc_config()
    state, nonce = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    request.session["oidc_state"], request.session["oidc_nonce"] = state, nonce
    query = urllib.parse.urlencode({"response_type": "code", "client_id": settings.OIDC_CLIENT_ID, "scope": "openid email profile",
                                    "redirect_uri": request.build_absolute_uri(reverse("integrations:sso_callback")),
                                    "state": state, "nonce": nonce})
    return redirect(f"{conf['authorization_endpoint']}?{query}")


def sso_callback(request):
    if request.GET.get("state") != request.session.get("oidc_state") or not request.GET.get("code"):
        messages.error(request, "Single sign-on failed. Please try again.")
        return redirect("accounts:login")
    conf = _oidc_config()
    body = urllib.parse.urlencode({"grant_type": "authorization_code", "code": request.GET["code"],
                                   "redirect_uri": request.build_absolute_uri(reverse("integrations:sso_callback")),
                                   "client_id": settings.OIDC_CLIENT_ID, "client_secret": settings.OIDC_CLIENT_SECRET}).encode()
    with urllib.request.urlopen(urllib.request.Request(conf["token_endpoint"], data=body), timeout=10) as r:
        tokens = json.loads(r.read())
    jwk_client = jwt.PyJWKClient(conf["jwks_uri"])
    key = jwk_client.get_signing_key_from_jwt(tokens["id_token"]).key
    claims = jwt.decode(tokens["id_token"], key, algorithms=["RS256", "ES256"], audience=settings.OIDC_CLIENT_ID,
                        issuer=conf["issuer"])
    if claims.get("nonce") != request.session.get("oidc_nonce"):
        messages.error(request, "Single sign-on failed (nonce).")
        return redirect("accounts:login")
    email = (claims.get("email") or "").lower()
    if not email or (settings.OIDC_ALLOWED_DOMAINS and email.split("@")[-1] not in settings.OIDC_ALLOWED_DOMAINS):
        messages.error(request, "Your organisation account isn't enabled for SportIQ single sign-on.")
        return redirect("accounts:login")
    ident = ExternalIdentity.objects.filter(provider="oidc", subject=claims["sub"]).select_related("user").first()
    user = ident.user if ident else User.objects.filter(email__iexact=email).first()
    if not user:
        user = User.objects.create_user(email=email, password=None, first_name=claims.get("given_name", ""),
                                        last_name=claims.get("family_name", ""), email_verified=True)
    ExternalIdentity.objects.get_or_create(provider="oidc", subject=claims["sub"], defaults={"user": user})
    login(request, user, backend="apps.accounts.backends.EmailBackend")
    audit(user, "account.sso_login", user, {"provider": settings.OIDC_PROVIDER_NAME}, request)
    return redirect("learning:dashboard")
