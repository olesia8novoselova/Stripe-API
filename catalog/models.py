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
    
# модель для хранения скидок
class Discount(models.Model):
    name = models.CharField(max_length=100)
    percent_off = models.PositiveIntegerField(help_text="Скидка в %")
    active = models.BooleanField(default=True)
    stripe_coupon_id = models.CharField(max_length=64, blank=True, default="")

    def __str__(self):
        st = "ACTIVE" if self.active else "INACTIVE"
        return f"{self.name} (-{self.percent_off}% | {st})"

# модель для хранения налогов
class Tax(models.Model):
    display_name = models.CharField(max_length=50, help_text="Название, напр. НДС")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Процент, напр. 20.00")
    inclusive = models.BooleanField(default=False, help_text="Включён в цену (True) или сверху (False)")
    active = models.BooleanField(default=True)
    stripe_tax_rate_id = models.CharField(max_length=64, blank=True, default="")

    def __str__(self):
        mode = "incl" if self.inclusive else "excl"
        st = "ACTIVE" if self.active else "INACTIVE"
        return f"{self.display_name} {self.percentage}% ({mode}, {st})"

# корзина из нескольких товаров одной валюты
class Order(models.Model):
    items = models.ManyToManyField(Item, related_name="orders")
    currency = models.CharField(max_length=3, default="usd")
    created_at = models.DateTimeField(auto_now_add=True)
    paid = models.BooleanField(default=False)

    discount = models.ForeignKey(Discount, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    taxes = models.ManyToManyField(Tax, blank=True, related_name="orders")

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

