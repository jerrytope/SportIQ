"""Public observatory, Android app link, identity verification (Phase 3-4)."""
import json
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.analytics.services import observatory as observatory_data
from apps.core.audit import audit
from apps.integrations.registry import IdentityVerification


def observatory(request):
    return render(request, "public/observatory.html", observatory_data())


def assetlinks(request):
    """Digital Asset Links for an Android Trusted Web Activity wrapper of the PWA (set ANDROID_APP_PACKAGE / ANDROID_CERT_SHA256)."""
    pkg, sha = os.getenv("ANDROID_APP_PACKAGE", ""), os.getenv("ANDROID_CERT_SHA256", "")
    data = [{"relation": ["delegate_permission/common.handle_all_urls"],
             "target": {"namespace": "android_app", "package_name": pkg, "sha256_cert_fingerprints": [sha]}}] if pkg and sha else []
    return JsonResponse(data, safe=False)


@login_required
@require_POST
def verify_identity(request):
    result = IdentityVerification().verify(request.user, request.POST.get("id_number", "").strip(), request.user)
    if result["status"] == "match":
        audit(request.user, "identity.verified", request.user, {"provider": result.get("provider")}, request)
        messages.success(request, "Identity confirmed.")
    elif result["status"] == "disabled":
        messages.info(request, "Identity verification isn't available on this platform yet.")
    else:
        messages.error(request, "We couldn't confirm that identity number.")
    return redirect("accounts:settings")
