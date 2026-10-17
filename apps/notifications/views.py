from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


@login_required
def notification_list(request):
    items = list(request.user.notifications.all()[:50])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "notifications/list.html", {"items": items})


@login_required
def open_notification(request, pk):
    n = get_object_or_404(request.user.notifications, pk=pk)
    n.is_read = True
    n.save(update_fields=["is_read"])
    if n.url and url_has_allowed_host_and_scheme(n.url, {request.get_host()}):
        return redirect(n.url)
    return redirect("notifications:list")


@login_required
@require_POST
def clear(request):
    request.user.notifications.all().delete()
    return redirect("notifications:list")
