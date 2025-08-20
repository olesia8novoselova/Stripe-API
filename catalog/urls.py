from django.urls import path
from .views import item_page, buy_item, buy_order, order_page, stripe_webhook

urlpatterns = [
    path("item/<int:id>/", item_page, name="item-page"),
    path("buy/<int:id>/", buy_item, name="buy-item"),

    path("order/<int:id>/", order_page, name="order-page"),
    path("buy-order/<int:id>/", buy_order, name="buy-order"),

    path("stripe/webhook/", stripe_webhook, name="stripe-webhook"),
]