from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .models import Item, CheckoutSession
from .services.stripe_api import create_checkout_session_for_item

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


# Stripe Webhook для подтверждения оплаты с проверкой подписи
@csrf_exempt
def stripe_webhook(request):
    import stripe

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=webhook_secret
        )
    except ValueError:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)

    # успешная оплата Checkout Session
    if event["type"] == "checkout.session.completed":
        data = event["data"]["object"]
        session_id = data.get("id")
        try:
            cs = CheckoutSession.objects.get(session_id=session_id)
            cs.paid = True
            cs.save(update_fields=["paid"])
        except CheckoutSession.DoesNotExist:
            pass

    return HttpResponse(status=200)