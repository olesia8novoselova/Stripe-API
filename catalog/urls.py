from django.urls import path
from .views import buy_item_intent, buy_order_intent, item_intent_page, item_page, buy_item, buy_order, order_intent_page, order_page, stripe_webhook

urlpatterns = [
    path("item/<int:id>/", item_page, name="item-page"),
    path("buy/<int:id>/", buy_item, name="buy-item"),

    path("order/<int:order_id>/", order_page, name="order-page"),
    path("buy-order/<int:order_id>/", buy_order, name="buy-order"),

    # PaymentIntent flow
    path("item-intent/<int:id>/", item_intent_page, name="item-intent-page"),
    path("buy-intent/<int:id>/", buy_item_intent, name="buy-item-intent"),

    path("order-intent/<int:order_id>/", order_intent_page, name="order-intent-page"),
    path("buy-order-intent/<int:order_id>/", buy_order_intent, name="buy-order-intent"),

    path("stripe/webhook/", stripe_webhook, name="stripe-webhook"),
]