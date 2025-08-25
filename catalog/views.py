from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.views.decorators.http import require_GET
import logging
from decimal import Decimal, ROUND_HALF_UP
import stripe

from .models import Item, CheckoutSession, Order, OrderPayment
from .services.stripe_api import create_checkout_session_for_item, create_checkout_session_for_order
from .services.stripe_api import create_payment_intent_for_item, create_payment_intent_for_order


log = logging.getLogger(__name__)

# возвращает publishable key под конкретную валюту
# порядок поиска: settings.get_stripe_publishable_for(cur), settings.STRIPE_KEYS[cur]['publishable'], settings.STRIPE_PUBLISHABLE_KEY
def _publishable_for_currency(currency: str) -> str:
    cur = (currency or getattr(settings, "DEFAULT_CURRENCY", "usd")).lower()

    # кастомный resolver из settings
    if hasattr(settings, "get_stripe_publishable_for"):
        try:
            key = settings.get_stripe_publishable_for(cur)
            if key:
                return key
        except Exception:
            pass

    keys = getattr(settings, "STRIPE_KEYS", None)
    if isinstance(keys, dict):
        pair = keys.get(cur) or keys.get(getattr(settings, "DEFAULT_CURRENCY", "usd"), {})
        if isinstance(pair, dict) and pair.get("publishable"):
            return pair["publishable"]

    # fallback — один общий публичный ключ
    return getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")

@require_GET
def item_page(request, id: int):
    item = get_object_or_404(Item, id=id)
    display_price = item.price / 100
    # ключ под валюту товара
    pubkey = _publishable_for_currency(item.currency)
    return render(request, "item.html", {
        "item": item,
        "display_price": f"{display_price:.2f}",
        "STRIPE_PUBLISHABLE_KEY": pubkey,
    })

@require_GET
def buy_item(request, id: int):
    item = get_object_or_404(Item, id=id)
    try:
        session = create_checkout_session_for_item(item)
    except ValueError as e:
        # предвалидации
        return JsonResponse({"error": str(e)}, status=400)
    except stripe.error.StripeError as e:
        # ошибки, которые вернул Stripe
        msg = getattr(e, "user_message", None) or str(e)
        return JsonResponse({"error": msg}, status=400)
    except Exception as e:
        log.exception("Ошибка buy_item(id=%s)", id)
        return JsonResponse({"error": f"Unexpected: {e}"}, status=500)

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

    # ключ под валюту заказа
    pubkey = _publishable_for_currency(order.currency)

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
        "STRIPE_PUBLISHABLE_KEY": pubkey, 
    }
    return render(request, "order.html", context)

@require_GET
def buy_order(request, order_id: int):
    order = get_object_or_404(Order, id=order_id)
    if order.items.count() == 0:
        return JsonResponse({"error": "Заказ пуст"}, status=400)
    try:
        session = create_checkout_session_for_order(order)
    except ValueError as e:
        # предвалидации (минимальная сумма, смешанные валюты и т.д.)
        return JsonResponse({"error": str(e)}, status=400)
    except stripe.error.StripeError as e:
        # ошибки от Stripe с понятным текстом
        msg = getattr(e, "user_message", None) or str(e)
        return JsonResponse({"error": msg}, status=400)
    except Exception as e:
        log.exception("Ошибка создания сессии Stripe (order_id=%s)", order_id)
        return JsonResponse({"error": f"Unexpected: {e}"}, status=500)

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

@require_GET
def item_intent_page(request, id: int):
    item = get_object_or_404(Item, id=id)
    display_price = item.price / 100
    pubkey = _publishable_for_currency(item.currency)
    return render(request, "item_intent.html", {
        "item": item,
        "display_price": f"{display_price:.2f}",
        "STRIPE_PUBLISHABLE_KEY": pubkey,
    })

@require_GET
def buy_item_intent(request, id: int):
    item = get_object_or_404(Item, id=id)
    try:
        intent = create_payment_intent_for_item(item)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except stripe.error.StripeError as e:
        msg = getattr(e, "user_message", None) or str(e)
        return JsonResponse({"error": msg}, status=400)
    except Exception as e:
        log.exception("Не удалось создать PaymentIntent для buy_item_intent(id=%s)", id)
        return JsonResponse({"error": f"Неизвестная ошибка: {e}"}, status=500)

    return JsonResponse({"client_secret": intent.client_secret})


@require_GET
def order_intent_page(request, order_id: int):
    order = get_object_or_404(Order, id=order_id)
    items = list(order.items.all())

    # расчёты те же, что и на /order/
    subtotal_cents = sum(i.price for i in items)
    percent = order.discount.percent_off if (order.discount and order.discount.active) else 0
    discount_cents = int(
        (Decimal(subtotal_cents) * Decimal(percent) / Decimal(100))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    taxable_base_cents = subtotal_cents - discount_cents

    taxes_ctx = []
    exclusive_total_cents = 0
    for t in order.taxes.filter(active=True):
        rate = Decimal(t.percentage)
        if t.inclusive:
            tax_amount = (Decimal(taxable_base_cents) * rate / (Decimal(100) + rate)) \
                         .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            tax_amount = int(tax_amount)
        else:
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

    pubkey = _publishable_for_currency(order.currency)
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
            {"name": tx["name"], "rate": tx["rate"], "inclusive": tx["inclusive"],
             "amount_display": fmt(tx["amount_cents"])}
            for tx in taxes_ctx
        ],
        "has_taxes": bool(taxes_ctx),
        "total_display": fmt(total_cents),
        "STRIPE_PUBLISHABLE_KEY": pubkey,
    }
    return render(request, "order_intent.html", context)

@require_GET
def buy_order_intent(request, order_id: int):
    order = get_object_or_404(Order, id=order_id)
    if order.items.count() == 0:
        return JsonResponse({"error": "Заказ пуст"}, status=400)
    try:
        intent = create_payment_intent_for_order(order)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except stripe.error.StripeError as e:
        msg = getattr(e, "user_message", None) or str(e)
        return JsonResponse({"error": msg}, status=400)
    except Exception as e:
        log.exception("Не удалось создать PaymentIntent для buy_order_intent(order_id=%s)", order_id)
        return JsonResponse({"error": f"Неизвестная ошибка: {e}"}, status=500)

    return JsonResponse({"client_secret": intent.client_secret})