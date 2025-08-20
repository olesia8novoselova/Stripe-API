from django.db import models

class Item(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField(help_text="Цена в минимальных единицах")
    currency = models.CharField(max_length=3, default='usd')

    def __str__(self):
        major = self.price / 100
        return f"{self.name} ({self.currency.upper()} {major:.2f})"

    @property
    def display_price(self):
        return f"{self.price / 100:.2f}"


# сохранение созданных Stripe Checkout Sessions
class CheckoutSession(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="checkout_sessions")
    session_id = models.CharField(max_length=255, unique=True)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "PAID" if self.paid else "UNPAID"
        return f"{self.session_id} -> {self.item.name} [{status}]"

# корзина из нескольких товаров одной валюты
class Order(models.Model):
    items = models.ManyToManyField(Item, related_name="orders")
    currency = models.CharField(max_length=3, default="usd")
    created_at = models.DateTimeField(auto_now_add=True)
    paid = models.BooleanField(default=False)

    @property
    def total_amount(self) -> int:
        return sum(i.price for i in self.items.all())

    def __str__(self):
        return f"Order #{self.pk or 'new'}"
    
# связка Stripe Checkout Session с Order
# помогаем webhook найти нужный заказ
class OrderPayment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    session_id = models.CharField(max_length=255, unique=True)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "PAID" if self.paid else "UNPAID"
        return f"{self.session_id} -> Order #{self.order_id} [{status}]"
