from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.notifications.services import notify

from .models import HelpArticle, HelpCategory, Ticket, TicketMessage


def help_centre(request):
    q = request.GET.get("q", "").strip()
    results = None
    if q:
        results = HelpArticle.objects.filter(is_published=True).filter(Q(title__icontains=q) | Q(body__icontains=q))
    return render(request, "support/help.html", {
        "categories": HelpCategory.objects.prefetch_related("articles"), "q": q, "results": results,
        "base": "app/base.html" if request.user.is_authenticated else "public/base.html",
    })


def article(request, slug):
    art = get_object_or_404(HelpArticle, slug=slug, is_published=True)
    return render(request, "support/article.html", {
        "article": art, "related": art.category.articles.filter(is_published=True).exclude(pk=art.pk)[:5],
        "base": "app/base.html" if request.user.is_authenticated else "public/base.html",
    })


def faqs(request):
    return render(request, "support/faqs.html", {
        "faqs": HelpArticle.objects.filter(is_faq=True, is_published=True).select_related("category"),
    })


class TicketForm(forms.ModelForm):
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}), label="Describe the problem")
    attachment = forms.FileField(required=False, label="Screenshot or document (optional)")

    class Meta:
        model = Ticket
        fields = ["category", "subject"]


@login_required
def my_tickets(request):
    form = TicketForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        t.user = request.user
        t.save()
        TicketMessage.objects.create(ticket=t, author=request.user, body=form.cleaned_data["message"],
                                     attachment=form.cleaned_data.get("attachment") or "")
        notify(request.user, f"Ticket {t.reference} received", f"We aim to respond by {t.sla_due:%d %b, %H:%M}.",
               f"/help/tickets/{t.pk}/")
        messages.success(request, f"Ticket {t.reference} created. We'll reply by email and here.")
        return redirect("support:ticket", pk=t.pk)
    return render(request, "support/my_tickets.html", {"tickets": request.user.tickets.all(), "form": form})


@login_required
def ticket(request, pk):
    t = get_object_or_404(Ticket, pk=pk, user=request.user)
    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            TicketMessage.objects.create(ticket=t, author=request.user, body=body[:10000])
            if t.status in ("pending", "resolved"):
                t.status = "open"
                t.save(update_fields=["status"])
            messages.success(request, "Reply sent.")
        if request.POST.get("action") == "close":
            t.status = "closed"
            t.save(update_fields=["status"])
        return redirect("support:ticket", pk=pk)
    return render(request, "support/ticket.html", {"ticket": t, "thread": t.messages.filter(is_internal=False).select_related("author")})
