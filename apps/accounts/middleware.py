from django.utils.cache import add_never_cache_headers


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
