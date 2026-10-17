from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render


def staff_required(*roles):
    """Back-office access. With roles, the user must hold one of them (super/NIS admins always pass)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not user.is_backoffice or (roles and not user.has_role(*roles)):
                return render(request, "manage/forbidden.html", status=403)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
