import io
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.catalog.models import Course

from . import services
from .models import Order, Voucher


@login_required
def checkout(request, slug):
    course = get_object_or_404(Course.objects.published(), slug=slug)
    if course.is_free:
        return redirect(course)
    if request.user.enrolments.filter(course=course).exists():
        return redirect("learning:course", slug=slug)
    voucher, voucher_error = None, None
    code = (request.POST.get("voucher") or request.GET.get("voucher") or "").strip().upper()
    if code:
        voucher = Voucher.objects.filter(code__iexact=code).first()
        if not voucher or not voucher.is_usable_for(course):
            voucher_error, voucher = "That code is not valid for this course.", None
    discount = course.price_kobo * voucher.discount_percent // 100 if voucher else 0
    if request.method == "POST" and request.POST.get("action") == "pay" and not voucher_error:
        order = services.create_order(request.user, course, voucher)
        if order.amount_kobo == 0:
            services.mark_paid(order)
            messages.success(request, "Scholarship applied. You're enrolled!")
            return redirect("learning:course", slug=slug)
        callback = request.build_absolute_uri(reverse("commerce:callback"))
        url = services.checkout_url(order, callback)
        return redirect(url or reverse("commerce:test_gateway", args=[order.reference]))
    return render(request, "commerce/checkout.html", {
        "course": course, "voucher": voucher, "voucher_error": voucher_error, "code": code,
        "discount": discount, "total": course.price_kobo - discount, "live": services.live_mode(),
    })


@login_required
def test_gateway(request, reference):
    """Stands in for Paystack when no secret key is configured (development and demos)."""
    if services.live_mode():
        raise Http404
    order = get_object_or_404(Order, reference=reference, user=request.user)
    if request.method == "POST":
        if request.POST.get("outcome") == "success":
            services.mark_paid(order, {"simulated": True})
            messages.success(request, f"Payment successful. You're enrolled in {order.course.title}.")
            return redirect("learning:course", slug=order.course.slug)
        order.status = Order.FAILED
        order.save(update_fields=["status"])
        messages.error(request, "Payment was not completed. You have not been charged.")
        return redirect("commerce:checkout", slug=order.course.slug)
    return render(request, "commerce/test_gateway.html", {"order": order})


@login_required
def callback(request):
    order = get_object_or_404(Order, reference=request.GET.get("reference", ""), user=request.user)
    if order.status != Order.PAID:
        try:
            ok = services.verify_with_gateway(order)
        except Exception:  # noqa: BLE001 - gateway unreachable; webhook will reconcile later
            ok = False
        if ok:
            services.mark_paid(order, order.provider_payload)
        else:
            messages.error(request, "We couldn't confirm your payment yet. If you were charged, it will be applied shortly.")
            return redirect("accounts:payments")
    messages.success(request, f"Payment confirmed. Welcome to {order.course.title}!")
    return redirect("learning:course", slug=order.course.slug)


@csrf_exempt
@require_POST
def webhook(request):
    if not services.valid_webhook(request.body, request.META.get("HTTP_X_PAYSTACK_SIGNATURE", "")):
        return HttpResponse(status=400)
    event = json.loads(request.body)
    if event.get("event") == "charge.success":
        data = event.get("data", {})
        order = Order.objects.filter(reference=data.get("reference")).first()
        if order and data.get("amount") == order.amount_kobo:
            services.mark_paid(order, data)
    return HttpResponse(status=200)


@login_required
def receipt(request, reference):
    order = get_object_or_404(Order, reference=reference)
    if order.user != request.user and not request.user.has_role("finance_officer"):
        raise Http404
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFillColor(colors.HexColor("#008751"))
    c.rect(0, h - 90, w, 90, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, h - 55, "SportIQ")
    c.setFont("Helvetica", 11)
    c.drawRightString(w - 40, h - 55, "RECEIPT")
    c.setFillColor(colors.HexColor("#0B3D2E"))
    y = h - 140
    rows = [("Receipt reference", order.reference), ("Date", order.paid_at.strftime("%d %B %Y %H:%M") if order.paid_at else "—"),
            ("Billed to", f"{order.user.get_full_name()} <{order.user.email}>"), ("Course", order.course.title),
            ("List price", f"NGN {order.list_price_kobo / 100:,.2f}"), ("Discount", f"NGN {order.discount_kobo / 100:,.2f}"
             + (f" ({order.voucher.code})" if order.voucher else "")), ("Amount paid", f"NGN {order.amount_kobo / 100:,.2f}"),
            ("Status", order.get_status_display()), ("Payment provider", order.provider.title())]
    for label, value in rows:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#6B7A72"))
        c.drawString(40, y, label)
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(colors.HexColor("#0B3D2E"))
        c.drawString(200, y, str(value)[:70])
        y -= 26
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.HexColor("#6B7A72"))
    c.drawString(40, 60, "National Institute for Sports · SportIQ Digital Sports Academy · " + settings.SITE_URL)
    c.showPage()
    c.save()
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename=f"receipt-{order.reference}.pdf", content_type="application/pdf")
