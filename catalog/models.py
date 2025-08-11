from django.db import models

class Item(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField(help_text="Цена в минимальных единицах (центах/копейках)")
    currency = models.CharField(max_length=3, default='usd')

    def __str__(self):
        major = self.price / 100
        return f"{self.name} ({self.currency.upper()} {major:.2f})"

# сохранение созданных Stripe Checkout Sessions
class CheckoutSession(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="checkout_sessions")
    session_id = models.CharField(max_length=255, unique=True)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "PAID" if self.paid else "UNPAID"
        return f"{self.session_id} -> {self.item.name} [{status}]"
