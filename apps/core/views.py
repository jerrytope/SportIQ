import logging

from django.shortcuts import render

log = logging.getLogger("apps.security")


def not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    return render(request, "errors/500.html", status=500)


def forbidden(request, exception=None):
    return render(request, "manage/forbidden.html", status=403)


def csrf_failure(request, reason=""):
    """Security-token mismatch (usually a stale page): explain how to recover and log the exact reason."""
    log.warning("CSRF failure on %s %s: %s (referer=%s, secure=%s)", request.method, request.path, reason,
                request.META.get("HTTP_REFERER", "-"), request.is_secure())
    return render(request, "errors/403_csrf.html", {"retry_url": request.path}, status=403)
