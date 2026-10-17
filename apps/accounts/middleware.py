from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import add_never_cache_headers

# Paths a signed-in user may reach before entering their two-factor code.
TWO_FACTOR_EXEMPT = ("/account/2fa/verify/", "/account/logout/", "/static/", "/media/", "/i18n/", "/sw.js",
                     "/manifest.webmanifest", "/offline/")


def _has_confirmed_device(user):
    from django_otp import devices_for_user

    return any(True for _ in devices_for_user(user, confirmed=True))


class TwoFactorMiddleware:
    """Two-factor authentication (blueprint §4).

    Anyone who has switched on an authenticator app must enter a code after signing in, before using the site.
    Staff entering the back office must also have one set up when REQUIRE_STAFF_2FA is on.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        user = request.user
        if user.is_authenticated and not user.is_verified() and not path.startswith(TWO_FACTOR_EXEMPT):
            if _has_confirmed_device(user):
                return redirect(f"{reverse('accounts:two_factor_verify')}?next={path}")
            if (
                getattr(settings, "REQUIRE_STAFF_2FA", False)
                and (path.startswith("/manage/") or path.startswith("/django-admin/"))
                and user.is_backoffice
                and not path.startswith("/account/2fa/setup/")
            ):
                return redirect(f"{reverse('accounts:two_factor_setup')}?next={path}")
        return self.get_response(request)


# Kept so existing references to the old name keep working.
StaffTwoFactorMiddleware = TwoFactorMiddleware


class PrivatePageCacheMiddleware:
    """Signed-in pages must not be stored by the browser, so Back after logout cannot show private data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, "user", None) is not None and request.user.is_authenticated \
                and not request.path.startswith(("/static/", "/media/")) and not response.has_header("Cache-Control"):
            add_never_cache_headers(response)  # max-age=0, no-cache, no-store, must-revalidate, private
        return response
