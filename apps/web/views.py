from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from apps.catalog.models import Course, LearningPath, Profession
from apps.notifications.services import send_email
from apps.support.models import HelpArticle

from .models import BlogPost, DemoRequest, Event, ImpactStat, NewsletterSubscriber, PartnerLogo, PressMention, Testimonial
from .pages import PAGES


def home(request):
    courses = list(Course.objects.visible_to(request.user).select_related("track").order_by("-featured", "-published_at")[:9])
    paths = LearningPath.objects.filter(is_published=True)[:1]
    professions = Profession.objects.prefetch_related("courses").all()
    role_courses = {
        p.pk: list(p.courses.filter(status=Course.PUBLISHED).order_by("-featured")[:3]) for p in professions
    }
    testimonials = list(Testimonial.objects.filter(is_active=True))
    return render(request, "public/home.html", {
        "courses": courses,
        "path": paths[0] if paths else None,
        "professions": professions,
        "role_courses": role_courses,
        "partners": PartnerLogo.objects.filter(is_active=True),
        "testimonials": testimonials,
        "press": PressMention.objects.filter(is_active=True)[:3],
        "posts": BlogPost.published()[:3],
        "stats": ImpactStat.objects.all(),
        "faqs": HelpArticle.objects.filter(is_faq=True, is_published=True)[:5],
    })


def about(request):
    return render(request, "public/about.html")


def institutions(request):
    return render(request, "public/institutions.html")


class DemoForm(forms.ModelForm):
    class Meta:
        model = DemoRequest
        fields = ["name", "email", "phone", "organisation", "organisation_type", "learners_estimate", "message"]
        widgets = {
            "organisation_type": forms.Select(choices=[("", "Select…"), ("NIS department", "NIS department"),
                                                       ("Federation", "Sports federation"),
                                                       ("State sports council", "State sports council"),
                                                       ("University", "University / college"),
                                                       ("Club / employer", "Club / employer"), ("Other", "Other")]),
            "learners_estimate": forms.Select(choices=[("", "Select…"), ("1-50", "1–50"), ("51-250", "51–250"),
                                                       ("251-1000", "251–1,000"), ("1000+", "More than 1,000")]),
            "message": forms.Textarea(attrs={"rows": 4, "placeholder": "What would you like to achieve?"}),
        }
        labels = {"learners_estimate": "How many people would you train?"}


def demo(request):
    form = DemoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.save()
        send_email(settings.DEFAULT_FROM_EMAIL, f"Demo request: {d.organisation}",
                   f"{d.name} <{d.email}> {d.phone}\n{d.organisation_type}, {d.learners_estimate}\n\n{d.message}")
        messages.success(request, "Thank you, we've received your request. Our team will contact you within two working days.")
        return redirect("web:demo")
    return render(request, "public/demo.html", {"form": form})


@require_POST
def newsletter(request):
    email = (request.POST.get("email") or "").strip().lower()
    try:
        forms.EmailField().clean(email)
    except forms.ValidationError:
        messages.error(request, "Please enter a valid email address.")
    else:
        NewsletterSubscriber.objects.update_or_create(email=email, defaults={"is_active": True})
        messages.success(request, "You're subscribed to the SportIQ newsletter.")
    return redirect(request.META.get("HTTP_REFERER") or "web:home")


def blog(request):
    return render(request, "public/blog_list.html", {"posts": BlogPost.published()})


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost.published(), slug=slug)
    more = BlogPost.published().exclude(pk=post.pk)[:3]
    return render(request, "public/blog_detail.html", {"post": post, "more": more})


def events(request):
    upcoming = Event.objects.filter(is_published=True, starts_at__gte=timezone.now())
    past = Event.objects.filter(is_published=True, starts_at__lt=timezone.now()).order_by("-starts_at")[:6]
    return render(request, "public/events.html", {"upcoming": upcoming, "past": past})


def page(request, slug):
    data = PAGES.get(slug)
    if not data:
        raise Http404
    return render(request, "public/page.html", {"page": data, "slug": slug})


def offline(request):
    return render(request, "public/offline.html")


def manifest(request):
    return JsonResponse({
        "name": "SportIQ — NIS Digital Sports Academy",
        "short_name": "SportIQ",
        "start_url": "/learn/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#008751",
        "icons": [{"src": "/static/img/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}],
    }, content_type="application/manifest+json")


@cache_control(max_age=0, no_cache=True)
def service_worker(request):
    js = (Path(settings.BASE_DIR) / "static" / "js" / "sw.js").read_text(encoding="utf-8")
    return HttpResponse(js, content_type="application/javascript")


def robots(request):
    return HttpResponse(f"User-agent: *\nDisallow: /manage/\nDisallow: /learn/\nDisallow: /account/\n"
                        f"Sitemap: {settings.SITE_URL}/sitemap.xml\n", content_type="text/plain")
