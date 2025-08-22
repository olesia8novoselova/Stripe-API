from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.views.decorators.http import require_GET
import logging
from decimal import Decimal, ROUND_HALF_UP

from .models import Item, CheckoutSession, Order, OrderPayment
from .services.stripe_api import create_checkout_session_for_item, create_checkout_session_for_order

log = logging.getLogger(__name__)

@require_GET
def item_page(request, id: int):
    item = get_object_or_404(Item, id=id)
    display_price = item.price / 100
    return render(request, "item.html", {
        "item": item,
        "display_price": f"{display_price:.2f}",
        "STRIPE_PUBLISHABLE_KEY": settings.STRIPE_PUBLISHABLE_KEY,
    })

@require_GET
def buy_item(request, id: int):
    item = get_object_or_404(Item, id=id)
    session = create_checkout_session_for_item(item)
    CheckoutSession.objects.create(item=item, session_id=session.id)
    return JsonResponse({"id": session.id})

@require_GET
def order_page(request, order_id: int):
    order = get_object_or_404(Order, id=order_id)
    items = list(order.items.all())

    # сумма позиций
    subtotal_cents = sum(i.price for i in items)

    # скидка на заказ
    percent = order.discount.percent_off if (order.discount and order.discount.active) else 0

    discount_cents = int(
        (Decimal(subtotal_cents) * Decimal(percent) / Decimal(100))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )

    # база для налогообложения (скидка уменьшает налоговую базу)
    taxable_base_cents = subtotal_cents - discount_cents

    taxes_ctx = []
    exclusive_total_cents = 0
    for t in order.taxes.filter(active=True):
        rate = Decimal(t.percentage)
        if t.inclusive:
            # из суммы выделяем налоговую часть
            tax_amount = (Decimal(taxable_base_cents) * rate / (Decimal(100) + rate)) \
                         .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            tax_amount = int(tax_amount)
        else:
            # начисляемый сверху налог
            tax_amount = (Decimal(taxable_base_cents) * rate / Decimal(100)) \
                         .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            tax_amount = int(tax_amount)
            exclusive_total_cents += tax_amount

        taxes_ctx.append({
            "name": t.display_name,
            "rate": f"{t.percentage}",
            "inclusive": t.inclusive,
            "amount_cents": tax_amount,
        })

    total_cents = taxable_base_cents + exclusive_total_cents

    def fmt(cents: int) -> str:
        return f"{cents / 100:.2f}"

    context = {
        "order": order,
        "items": items,
        "currency": order.currency.upper(),

        "subtotal_display": fmt(subtotal_cents),
        "has_discount": percent > 0,
        "discount_name": order.discount.name if percent > 0 else "",
        "discount_percent": percent,
        "discount_amount_display": fmt(discount_cents),

        "taxes": [
            {
                "name": tx["name"],
                "rate": tx["rate"],
                "inclusive": tx["inclusive"],
                "amount_display": fmt(tx["amount_cents"]),
            } for tx in taxes_ctx
        ],
        "has_taxes": bool(taxes_ctx),

        "total_display": fmt(total_cents),
        "STRIPE_PUBLISHABLE_KEY": settings.STRIPE_PUBLISHABLE_KEY,
    }
    return render(request, "order.html", context)

@require_GET
def buy_order(request, order_id: int):
    order = get_object_or_404(Order, id=order_id)
    if order.items.count() == 0:
        return JsonResponse({"error": "Order has no items"}, status=400)
    try:
        session = create_checkout_session_for_order(order)
    except Exception as e:
        log.exception("Stripe session create failed (order_id=%s)", order_id)
        return JsonResponse({"error": str(e)}, status=500)

    OrderPayment.objects.create(order=order, session_id=session.id)
    return JsonResponse({"id": session.id})

# Stripe Webhook для подтверждения оплаты с проверкой подписи
@csrf_exempt
def stripe_webhook(request):
    import stripe
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret:
        log.error("STRIPE_WEBHOOK_SECRET не установлен")
        return HttpResponse(status=500)

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=secret)
    except Exception:
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        data = event["data"]["object"]
        session_id = data.get("id")

        # одиночная покупка Item
        try:
            cs = CheckoutSession.objects.get(session_id=session_id)
            if not cs.paid:
                cs.paid = True
                cs.save(update_fields=["paid"])
        except CheckoutSession.DoesNotExist:
            cs = None

        # оплата заказа
        try:
            op = OrderPayment.objects.select_related("order").get(session_id=session_id)
            changed = False
            if not op.paid:
                op.paid = True
                op.save(update_fields=["paid"])
                changed = True

            if not op.order.paid:
                op.order.paid = True
                op.order.save(update_fields=["paid"])
                changed = True
            if changed:
                log.info("Заказ %s отмечен как PAID через сессию %s", op.order_id, session_id)
        except OrderPayment.DoesNotExist:
            pass