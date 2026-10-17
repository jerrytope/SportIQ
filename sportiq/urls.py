from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

from apps.web import views as web_views
from apps.web import views_phase4
from apps.web.sitemaps import SITEMAPS

admin.site.site_header = "SportIQ technical admin"

urlpatterns = [
    path("", include("apps.web.urls")),
    path("account/", include("apps.accounts.urls")),
    path("courses/", include("apps.catalog.urls")),
    path("learn/", include("apps.learning.urls")),
    path("", include("apps.credentials.urls")),
    path("", include("apps.commerce.urls")),
    path("help/", include("apps.support.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("manage/", include("apps.backoffice.urls")),
    path("practicals/", include("apps.practicals.urls")),
    path("live/", include("apps.live.urls")),
    path("library/", include("apps.library.urls")),
    path("careers/", include("apps.careers.urls")),
    path("ai/", include("apps.ai.urls")),
    path("labs/", include("apps.labs.urls")),
    path("community/", include("apps.community.urls")),
    path("workforce/", include("apps.workforce.urls")),
    path("research/", include("apps.research.urls")),
    path("integrity/", include("apps.integrity.urls")),
    path("", include("apps.integrations.urls")),
    path("observatory/", views_phase4.observatory, name="observatory"),
    path("account/verify-identity/", views_phase4.verify_identity, name="verify_identity"),
    path(".well-known/assetlinks.json", views_phase4.assetlinks),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/", include("apps.core.api_urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularRedocView.as_view(url_name="schema"), name="api_docs"),
    path("django-admin/", admin.site.urls),
    path("manifest.webmanifest", web_views.manifest, name="manifest"),
    path("sw.js", web_views.service_worker, name="sw"),
    path("robots.txt", web_views.robots),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"
handler403 = "apps.core.views.forbidden"
