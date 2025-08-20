from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import logging

from .models import Item, CheckoutSession, Order, OrderPayment
from .services.stripe_api import create_checkout_session_for_item, create_checkout_session_for_order

log = logging.getLogger(__name__)

def item_page(request, id: int):
    item = get_object_or_404(Item, id=id)
    display_price = item.price / 100
    return render(request, "item.html", {
        "item": item,
        "display_price": f"{display_price:.2f}",
        "STRIPE_PUBLISHABLE_KEY": settings.STRIPE_PUBLISHABLE_KEY,
    })

def buy_item(request, id: int):
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")
    item = get_object_or_404(Item, id=id)
    session = create_checkout_session_for_item(item)
    CheckoutSession.objects.create(item=item, session_id=session.id)
    return JsonResponse({"id": session.id})

def order_page(request, id: int):
    order = get_object_or_404(Order, id=id)
    items = list(order.items.all())
    total = order.total_amount / 100
    return render(request, "order.html", {
        "order": order,
        "items": items,
        "total_display": f"{total:.2f}",
        "STRIPE_PUBLISHABLE_KEY": settings.STRIPE_PUBLISHABLE_KEY,
    })

def buy_order(request, id: int):
    order = get_object_or_404(Order, id=id)
    if order.items.count() == 0:
        return JsonResponse({"error": "Order has no items"}, status=400)
    try:
        session = create_checkout_session_for_order(order)
    except Exception as e:
        log.exception("Ошибка создания сессии Stripe (заказ)")
        return JsonResponse({"error": str(e)}, status=500)

    # сохраняем связь session с order
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