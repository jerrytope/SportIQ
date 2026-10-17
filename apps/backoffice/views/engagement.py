from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.core.audit import audit
from apps.core.models import SiteSettings
from apps.notifications.models import Announcement, Campaign
from apps.notifications.services import audience_users, notify, send_campaign
from apps.support.models import HelpArticle, StatusNotice, Ticket, TicketMessage
from apps.web.models import DemoRequest, NewsletterSubscriber

from ..decorators import staff_required
from ..forms import (SITE_CONTENT, AnnouncementForm, CampaignForm, HelpArticleForm, SiteSettingsForm,
                     StatusNoticeForm, site_form_class)


@staff_required("support_agent")
def tickets(request):
    qs = Ticket.objects.select_related("user", "assignee")
    view = request.GET.get("view", "open")
    if view == "mine":
        qs = qs.filter(assignee=request.user).exclude(status="closed")
    elif view == "overdue":
        qs = qs.filter(status__in=["open", "pending"], sla_due__lt=timezone.now())
    elif view == "all":
        pass
    else:
        qs = qs.filter(status__in=["open", "pending"])
    if request.GET.get("category"):
        qs = qs.filter(category=request.GET["category"])
    return render(request, "manage/support/tickets.html", {"tickets": qs, "view": view, "categories": Ticket.CATEGORIES})


@staff_required("support_agent")
def ticket_detail(request, pk):
    t = get_object_or_404(Ticket.objects.select_related("user"), pk=pk)
    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        internal = request.POST.get("internal") == "1"
        if body:
            TicketMessage.objects.create(ticket=t, author=request.user, body=body, is_internal=internal)
            if not internal:
                t.first_response_at = t.first_response_at or timezone.now()
                notify(t.user, f"Reply on {t.reference}: {t.subject}", body[:300], f"/help/tickets/{t.pk}/")
        for field in ("status", "priority"):
            val = request.POST.get(field)
            if val and val != getattr(t, field):
                setattr(t, field, val)
        assignee = request.POST.get("assignee")
        if assignee is not None:
            t.assignee_id = int(assignee) if assignee.isdigit() else None
        if t.status in ("resolved", "closed") and not t.resolved_at:
            t.resolved_at = timezone.now()
        t.save()
        messages.success(request, "Ticket updated.")
        return redirect("backoffice:ticket_detail", pk=pk)
    return render(request, "manage/support/ticket.html", {
        "ticket": t, "thread": t.messages.select_related("author"), "agents": User.objects.exclude(staff_roles=[]),
        "statuses": Ticket.STATUSES, "priorities": Ticket.PRIORITIES,
        "other_tickets": t.user.tickets.exclude(pk=t.pk)[:5],
    })


@staff_required("support_agent")
def help_articles(request):
    form = HelpArticleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Article published.")
        return redirect("backoffice:help_articles")
    return render(request, "manage/support/articles.html", {"articles": HelpArticle.objects.select_related("category"), "form": form})


@staff_required("support_agent")
def help_article_edit(request, pk):
    art = get_object_or_404(HelpArticle, pk=pk)
    if request.method == "POST" and request.POST.get("action") == "delete":
        art.delete()
        messages.success(request, "Article deleted.")
        return redirect("backoffice:help_articles")
    form = HelpArticleForm(request.POST or None, instance=art)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Article saved.")
        return redirect("backoffice:help_articles")
    return render(request, "manage/simple_form.html", {"form": form, "title": f"Edit: {art.title}",
                                                       "back_url": "backoffice:help_articles", "delete": True})


@staff_required("support_agent", "comms_officer")
def status_notices(request):
    form = StatusNoticeForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("action") == "end":
            StatusNotice.objects.filter(pk=request.POST.get("notice")).update(is_active=False)
            messages.success(request, "Notice ended.")
        elif form.is_valid():
            form.save()
            messages.success(request, "Notice published. It now shows on every page.")
        return redirect("backoffice:status_notices")
    return render(request, "manage/support/notices.html", {"notices": StatusNotice.objects.all()[:30], "form": form})


@staff_required("comms_officer")
def comms(request):
    a_form = AnnouncementForm(request.POST if request.POST.get("form") == "announcement" else None, prefix="a")
    c_form = CampaignForm(request.POST if request.POST.get("form") == "campaign" else None, prefix="c")
    if request.method == "POST":
        if request.POST.get("form") == "announcement" and a_form.is_valid():
            a = a_form.save(commit=False)
            a.created_by = request.user
            a.save()
            messages.success(request, "Announcement published to learner dashboards.")
            return redirect("backoffice:comms")
        if request.POST.get("form") == "campaign" and c_form.is_valid():
            c = c_form.save(commit=False)
            c.created_by = request.user
            c.save()
            n = send_campaign(c)
            audit(request.user, "campaign.sent", c, {"channel": c.channel, "recipients": n}, request)
            messages.success(request, f"Sent to {n} recipient(s).")
            return redirect("backoffice:comms")
        if request.POST.get("action") == "toggle":
            a = get_object_or_404(Announcement, pk=request.POST.get("announcement"))
            a.is_active = not a.is_active
            a.save(update_fields=["is_active"])
            return redirect("backoffice:comms")
    return render(request, "manage/comms.html", {
        "a_form": a_form, "c_form": c_form, "announcements": Announcement.objects.all()[:20],
        "campaigns": Campaign.objects.all()[:20],
    })


@staff_required("comms_officer")
def site_content(request):
    settings_form = SiteSettingsForm(request.POST or None, instance=SiteSettings.load())
    if request.method == "POST":
        if request.POST.get("action") == "demo_status":
            DemoRequest.objects.filter(pk=request.POST.get("demo")).update(status=request.POST.get("status", "contacted"))
            return redirect("backoffice:site")
        if settings_form.is_valid():
            settings_form.save()
            audit(request.user, "site.settings_updated", None, {"fields": settings_form.changed_data}, request)
            messages.success(request, "Landing page updated.")
            return redirect("backoffice:site")
    sections = [(k, label, model.objects.count()) for k, (model, _, label) in SITE_CONTENT.items()]
    return render(request, "manage/site/index.html", {
        "form": settings_form, "sections": sections, "demos": DemoRequest.objects.all()[:20],
        "subscribers": NewsletterSubscriber.objects.filter(is_active=True).count(),
    })


@staff_required("comms_officer")
def site_list(request, kind):
    if kind not in SITE_CONTENT:
        raise Http404
    model, fields, label = SITE_CONTENT[kind]
    return render(request, "manage/site/list.html", {"kind": kind, "label": label, "items": model.objects.all(),
                                                     "first_field": fields[0]})


@staff_required("comms_officer")
def site_edit(request, kind, pk):
    if kind not in SITE_CONTENT:
        raise Http404
    model, _, label = SITE_CONTENT[kind]
    obj = model.objects.filter(pk=pk).first() if pk else None
    if pk and not obj:
        raise Http404
    if request.method == "POST" and request.POST.get("action") == "delete" and obj:
        obj.delete()
        messages.success(request, "Deleted.")
        return redirect("backoffice:site_list", kind=kind)
    Form = site_form_class(kind)
    form = Form(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if kind == "blog" and not item.author_id:
            item.author = request.user
        item.save()
        messages.success(request, "Saved.")
        return redirect("backoffice:site_list", kind=kind)
    return render(request, "manage/simple_form.html", {
        "form": form, "title": f"{'Edit' if obj else 'Add'}: {label.rstrip('s')}", "back_url": "backoffice:site_list",
        "back_arg": kind, "delete": bool(obj), "multipart": True,
    })
