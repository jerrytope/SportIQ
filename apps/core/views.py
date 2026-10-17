from django.shortcuts import render


def not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    return render(request, "errors/500.html", status=500)


def forbidden(request, exception=None):
    return render(request, "manage/forbidden.html", status=403)
