from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.catalog.models import Course, LearningPath

from .models import BlogPost
from .pages import PAGES


class StaticSitemap(Sitemap):
    def items(self):
        return ["web:home", "web:about", "web:institutions", "web:demo", "web:blog", "web:events", "catalog:list",
                "catalog:paths", "credentials:verify", "support:faqs", "support:help"]

    def location(self, item):
        return reverse(item)


class PageSitemap(Sitemap):
    def items(self):
        return list(PAGES)

    def location(self, item):
        return reverse("web:page", args=[item])


class CourseSitemap(Sitemap):
    def items(self):
        return Course.objects.published().filter(is_public=True)

    def lastmod(self, obj):
        return obj.updated_at


class PathSitemap(Sitemap):
    def items(self):
        return LearningPath.objects.filter(is_published=True)


class BlogSitemap(Sitemap):
    def items(self):
        return BlogPost.published()

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {"static": StaticSitemap, "pages": PageSitemap, "courses": CourseSitemap, "paths": PathSitemap,
            "blog": BlogSitemap}
