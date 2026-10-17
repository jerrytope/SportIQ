from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils.translation import get_language

from .models import FORMATS, LANGUAGES, LEVELS, Course, LearningPath, Profession, Sport, Track


def course_list(request):
    qs = Course.objects.visible_to(request.user).select_related("track").distinct()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(description__icontains=q)
                       | Q(track__name__icontains=q) | Q(code__icontains=q))
    filters = {
        "track": ("track__slug", Track.objects.all()),
        "profession": ("professions__slug", Profession.objects.all()),
        "sport": ("sports__slug", Sport.objects.all()),
    }
    for key, (lookup, _) in filters.items():
        if request.GET.get(key):
            qs = qs.filter(**{lookup: request.GET[key]})
    for key, field in (("level", "level"), ("format", "delivery_format"), ("language", "language")):
        if request.GET.get(key):
            qs = qs.filter(**{field: request.GET[key]})
    price = request.GET.get("price")
    if price == "free":
        qs = qs.filter(price_kobo=0)
    elif price == "paid":
        qs = qs.filter(price_kobo__gt=0)
    sort = request.GET.get("sort", "featured")
    qs = qs.order_by({"newest": "-published_at", "title": "title", "shortest": "duration_hours"}.get(sort, "-featured"), "title")
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    return render(request, "catalog/list.html", {
        "page": page, "q": q, "tracks": Track.objects.all(), "professions": Profession.objects.all(),
        "sports": Sport.objects.filter(courses__status=Course.PUBLISHED).distinct(), "levels": LEVELS,
        "formats": FORMATS, "languages": LANGUAGES, "total": qs.count(),
        "base": "app/base.html" if request.user.is_authenticated else "public/base.html",
    })


def course_detail(request, slug):
    course = get_object_or_404(Course.objects.select_related("track", "institution", "owner", "credential_type"), slug=slug)
    user = request.user
    is_staff_preview = user.is_authenticated and (user.is_backoffice or course.owner_id == user.pk)
    if course.status != Course.PUBLISHED and not is_staff_preview:
        from django.http import Http404

        raise Http404
    enrolment = application = None
    missing = []
    if user.is_authenticated:
        from apps.learning.services import prerequisites_missing

        enrolment = user.enrolments.filter(course=course).first()
        application = user.applications.filter(course=course).first()
        missing = prerequisites_missing(user, course)
    modules = course.modules.prefetch_related("lessons")
    stats = course.enrolments.aggregate(n=Count("pk"))
    rating = course.enrolments.filter(feedback__isnull=False).aggregate(avg=Avg("feedback__course_rating"), n=Count("feedback"))
    return render(request, "catalog/detail.html", {
        "course": course, "modules": modules, "enrolment": enrolment, "application": application,
        "missing": missing, "learners": stats["n"], "rating": rating, "exam": course.final_exam(),
        "related": Course.objects.published().filter(track=course.track).exclude(pk=course.pk)[:3],
        "base": "app/base.html" if user.is_authenticated else "public/base.html",
        "preview": course.status != Course.PUBLISHED,
        "tr": course.translation_for(get_language()),
    })


def path_list(request):
    return render(request, "catalog/paths.html", {
        "paths": LearningPath.objects.filter(is_published=True).prefetch_related("items__course"),
        "base": "app/base.html" if request.user.is_authenticated else "public/base.html",
    })


def path_detail(request, slug):
    path = get_object_or_404(LearningPath, slug=slug, is_published=True)
    items = path.items.select_related("course", "course__track")
    done = set()
    enrolled = set()
    if request.user.is_authenticated:
        done = set(request.user.enrolments.filter(status="completed").values_list("course_id", flat=True))
        enrolled = set(request.user.enrolments.values_list("course_id", flat=True))
    return render(request, "catalog/path_detail.html", {
        "path": path, "items": items, "done": done, "enrolled": enrolled,
        "pct": round(100 * len([i for i in items if i.course_id in done]) / len(items)) if items else 0,
        "base": "app/base.html" if request.user.is_authenticated else "public/base.html",
    })
