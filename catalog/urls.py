from django.urls import path
from .views import item_page, buy_item, stripe_webhook

urlpatterns = [
    path("item/<int:id>/", item_page, name="item-page"),
    path("buy/<int:id>/", buy_item, name="buy-item"),
    path("stripe/webhook/", stripe_webhook, name="stripe-webhook"),
]