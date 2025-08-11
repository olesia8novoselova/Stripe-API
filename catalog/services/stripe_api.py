import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

# Функция для создания Stripe Checkout Session для одного товара
# Возвращает объект session (dict-like) с .id
def create_checkout_session_for_item(item):
    product_data = {"name": item.name}
    if item.description:
        product_data["description"] = item.description

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": item.currency,
                "product_data": product_data,
                "unit_amount": int(item.price),
            },
            "quantity": 1,
        }],
        success_url=settings.SUCCESS_URL,
        cancel_url=settings.CANCEL_URL,
    )
    return session