import os

from django.conf import settings

from .models import SiteSettings


def site(request):
    from apps.support.models import StatusNotice

    ctx = {
        "site": SiteSettings.load(),
        "status_notices": StatusNotice.current(),
        "SITE_URL": settings.SITE_URL,
        "ASSET_V": _asset_version(),
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_count"] = user.notifications.filter(is_read=False).count()
    return ctx


def _asset_version():
    """Cache-buster for CSS/JS in development (production uses hashed filenames)."""
    if not settings.DEBUG:
        return ""
    base = settings.BASE_DIR / "static"
    return str(int(max(os.path.getmtime(base / "css" / "sportiq.css"), os.path.getmtime(base / "js" / "sportiq.js"))))
