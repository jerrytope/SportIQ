from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Sport, Track

from .models import Annotation, Collection, Resource


def _base(request):
    return "app/base.html" if request.user.is_authenticated else "public/base.html"


def visible_qs(user):
    qs = Resource.objects.filter(is_published=True)
    if not user.is_authenticated:
        return qs.filter(access_level="public")
    if user.is_backoffice:
        return qs
    return qs.filter(Q(access_level__in=["public", "learners"]) | Q(access_grants__user=user)).distinct()


def index(request):
    qs = visible_qs(request.user).select_related("track")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(abstract__icontains=q) | Q(authors__icontains=q) | Q(tags__icontains=q))
    for key, lookup in (("kind", "kind"), ("track", "track__slug"), ("sport", "sports__slug")):
        if request.GET.get(key):
            qs = qs.filter(**{lookup: request.GET[key]})
    page = Paginator(qs.distinct(), 18).get_page(request.GET.get("page"))
    return render(request, "library/index.html", {
        "page": page, "q": q, "kinds": Resource.KINDS, "tracks": Track.objects.all(), "sports": Sport.objects.all(),
        "base": _base(request), "collections": request.user.collections.all() if request.user.is_authenticated else [],
        "hidden_count": Resource.objects.filter(is_published=True).count() - visible_qs(request.user).count(),
    })


def detail(request, slug):
    r = get_object_or_404(Resource, slug=slug, is_published=True)
    if not r.visible_to(request.user):
        if not request.user.is_authenticated:
            return redirect(f"/account/login/?next={request.path}")
        raise Http404
    related = visible_qs(request.user).filter(Q(track=r.track) | Q(kind=r.kind)).exclude(pk=r.pk)[:4]
    return render(request, "library/detail.html", {
        "r": r, "related": related, "base": _base(request), "versions": r.versions.all(),
        "citations": {"APA": r.citation("apa"), "Harvard": r.citation("harvard"), "BibTeX": r.citation("bibtex")},
        "annotations": r.annotations.filter(user=request.user) if request.user.is_authenticated else [],
        "collections": request.user.collections.all() if request.user.is_authenticated else [],
    })


def download(request, slug):
    r = get_object_or_404(Resource, slug=slug, is_published=True)
    if not r.visible_to(request.user) or not r.file:
        raise Http404
    Resource.objects.filter(pk=r.pk).update(downloads=F("downloads") + 1)
    return FileResponse(r.file.open("rb"), as_attachment=True, filename=r.file.name.split("/")[-1])


def cite(request, slug, style):
    r = get_object_or_404(Resource, slug=slug, is_published=True)
    if style not in ("apa", "harvard", "bibtex") or not r.visible_to(request.user):
        raise Http404
    ext = "bib" if style == "bibtex" else "txt"
    resp = HttpResponse(r.citation(style), content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{r.slug}.{ext}"'
    return resp


@login_required
@require_POST
def annotate(request, slug):
    r = get_object_or_404(Resource, slug=slug, is_published=True)
    if r.visible_to(request.user) and request.POST.get("note", "").strip():
        Annotation.objects.create(user=request.user, resource=r, note=request.POST["note"][:4000],
                                  page=request.POST.get("page", "")[:20])
    return redirect(f"{r.get_absolute_url()}#notes")


@login_required
@require_POST
def collect(request, slug):
    r = get_object_or_404(Resource, slug=slug, is_published=True)
    name = request.POST.get("new_collection", "").strip()
    if name:
        col, _ = Collection.objects.get_or_create(user=request.user, name=name[:120])
    else:
        col = get_object_or_404(Collection, pk=request.POST.get("collection"), user=request.user)
    col.resources.add(r)
    messages.success(request, f"Saved to “{col.name}”.")
    return redirect(r.get_absolute_url())


@login_required
def collections(request):
    reading_lists = Collection.objects.filter(is_reading_list=True, course__enrolments__user=request.user).distinct()
    return render(request, "library/collections.html", {
        "mine": request.user.collections.prefetch_related("resources"), "reading_lists": reading_lists.prefetch_related("resources"),
        "notes": request.user.annotations.select_related("resource")[:30],
    })
