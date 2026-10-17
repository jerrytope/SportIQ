import csv
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.commerce import services as commerce
from apps.commerce.models import Order, Refund, Voucher
from apps.core.audit import audit

from ..decorators import staff_required
from ..forms import VoucherForm


@staff_required("finance_officer")
def finance(request):
    qs = Order.objects.select_related("user", "course", "voucher")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(reference__icontains=q) | Q(user__email__icontains=q) | Q(course__title__icontains=q))
    if request.method == "POST" and request.POST.get("action") == "reconcile":
        n = Order.objects.filter(pk__in=request.POST.getlist("orders"), status="paid").update(reconciled=True)
        audit(request.user, "payments.reconciled", None, {"count": n}, request)
        messages.success(request, f"Marked {n} payment(s) as reconciled.")
        return redirect("backoffice:finance")
    paid = Order.objects.filter(status__in=["paid", "refunded"])
    return render(request, "manage/finance/list.html", {
        "orders": qs[:200], "status": status, "q": q, "statuses": Order.STATUSES,
        "totals": {
            "gross": (paid.aggregate(s=Sum("amount_kobo"))["s"] or 0) / 100,
            "refunds": (Refund.objects.aggregate(s=Sum("amount_kobo"))["s"] or 0) / 100,
            "unreconciled": Order.objects.filter(status="paid", reconciled=False).count(),
            "sponsored": Order.objects.filter(status="paid", amount_kobo=0).count(),
        },
        "live": commerce.live_mode(),
    })


@staff_required("finance_officer")
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("user", "course", "voucher"), pk=pk)
    if request.method == "POST" and request.POST.get("action") == "refund":
        try:
            amount = int(Decimal(request.POST.get("amount", "0")) * 100)
        except InvalidOperation:
            amount = 0
        reason = request.POST.get("reason", "").strip()
        already = order.refunds.aggregate(s=Sum("amount_kobo"))["s"] or 0
        if amount <= 0 or amount + already > order.amount_kobo or not reason:
            messages.error(request, "Enter a reason and an amount no greater than the remaining paid amount.")
        else:
            try:
                commerce.refund(order, amount, reason, request.user, request)
                messages.success(request, "Refund processed.")
            except Exception as exc:  # noqa: BLE001 - surface gateway errors to the officer
                messages.error(request, f"Refund failed: {exc}")
        return redirect("backoffice:order_detail", pk=pk)
    return render(request, "manage/finance/order.html", {"order": order, "refunds": order.refunds.select_related("processed_by")})


@staff_required("finance_officer")
def vouchers(request):
    form = VoucherForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        v = form.save(commit=False)
        v.code = v.code.upper()
        v.save()
        audit(request.user, "voucher.created", v, {"discount": v.discount_percent, "uses": v.max_uses}, request)
        messages.success(request, f"Code {v.code} created.")
        return redirect("backoffice:vouchers")
    return render(request, "manage/finance/vouchers.html", {
        "vouchers": Voucher.objects.select_related("course", "sponsor").annotate(n=Count("order")), "form": form})


@staff_required("finance_officer")
def finance_export(request):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="sportiq-payments.csv"'
    w = csv.writer(resp)
    w.writerow(["Reference", "Date", "Learner", "Email", "Course", "List (NGN)", "Discount (NGN)", "Paid (NGN)",
                "Voucher", "Status", "Reconciled"])
    for o in Order.objects.select_related("user", "course", "voucher"):
        w.writerow([o.reference, o.created_at.date(), o.user.get_full_name(), o.user.email, o.course.title,
                    o.list_price_kobo / 100, o.discount_kobo / 100, o.amount_kobo / 100,
                    o.voucher.code if o.voucher else "", o.status, o.reconciled])
    audit(request.user, "payments.exported", None, request=request)
    return resp
