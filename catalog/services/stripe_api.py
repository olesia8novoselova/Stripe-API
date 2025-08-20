import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

def _product_data_for_item(item):
    data = {"name": item.name}
    if item.description:
        data["description"] = item.description
    return data

# Функция для создания Stripe Checkout Session для одного товара
# Возвращает объект session (dict-like) с .id
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
        raise ValueError("Order has no items")

    currencies = {i.currency.lower() for i in items_qs}
    if len(currencies) > 1:
        raise ValueError("Mixed currencies are not supported in one Checkout")

    currency = next(iter(currencies))

    line_items = [{
        "price_data": {
            "currency": currency,
            "product_data": _product_data_for_item(item),
            "unit_amount": int(item.price),
        },
        "quantity": 1,
    } for item in items_qs]

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        client_reference_id=str(order.id),
        metadata={"order_id": str(order.id)},
        success_url=settings.SUCCESS_URL,
        cancel_url=settings.CANCEL_URL,
    )
    return session