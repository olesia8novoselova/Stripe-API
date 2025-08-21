import stripe
from django.conf import settings
from ..models import Discount

stripe.api_key = settings.STRIPE_SECRET_KEY

def _product_data_for_item(item):
    data = {"name": item.name}
    if item.description:
        data["description"] = item.description
    return data

# Функция для создания Stripe Checkout Session для одного товара
def create_checkout_session_for_item(item):
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": (item.currency or "usd").lower(),
                "product_data": _product_data_for_item(item),
                "unit_amount": int(item.price),
            },
            "quantity": 1,
        }],
        success_url=settings.SUCCESS_URL,
        cancel_url=settings.CANCEL_URL,
    )
    return session

# Функция для создания Stripe Checkout Session для заказа
def create_checkout_session_for_order(order):
    items_qs = order.items.all()
    if not items_qs.exists():
        raise ValueError("Заказ не содержит товаров")

    currencies = {i.currency.lower() for i in items_qs}
    if len(currencies) > 1:
        raise ValueError("Смешанные валюты не поддерживаются в одном чеке")

    currency = next(iter(currencies))

    line_items = [{
        "price_data": {
            "currency": currency,
            "product_data": _product_data_for_item(item),
            "unit_amount": int(item.price),
        },
        "quantity": 1,
    } for item in items_qs]

    params = dict(
        mode="payment",
        line_items=line_items,
        client_reference_id=str(order.id),
        metadata={"order_id": str(order.id)},
        success_url=settings.SUCCESS_URL,
        cancel_url=settings.CANCEL_URL,
    )

    # применяем скидку
    if order.discount and order.discount.active:
        coupon_id = ensure_stripe_coupon(order.discount)
        params["discounts"] = [{"coupon": coupon_id}]

    session = stripe.checkout.Session.create(**params)
    return session


# гарантируем наличие купона в Stripe и возвращаем его id
def ensure_stripe_coupon(discount: Discount) -> str:
    if discount.stripe_coupon_id and discount.active:
        return discount.stripe_coupon_id

    coupon = stripe.Coupon.create(
        percent_off=int(discount.percent_off),
        duration="once",
        name=discount.name,
    )
    discount.stripe_coupon_id = coupon.id
    discount.save(update_fields=["stripe_coupon_id"])
    return coupon.id