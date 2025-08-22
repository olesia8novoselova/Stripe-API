from django.contrib import admin
from .models import Item, CheckoutSession, Order, OrderPayment, Discount, Tax

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "display_price", "currency")
    list_filter = ("currency",)
    search_fields = ("name",)

@admin.register(CheckoutSession)
class CheckoutSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id", "item", "paid", "created_at")
    list_filter = ("paid", "item__currency")
    search_fields = ("session_id", "item__name")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "paid", "currency", "created_at", "total_amount_display", "discount")
    list_filter = ("paid", "currency", "discount")
    filter_horizontal = ("items", "taxes")

    def total_amount_display(self, obj):
        return f"{obj.currency.upper()} {obj.total_amount/100:.2f}"
    total_amount_display.short_description = "Total"

@admin.register(OrderPayment)
class OrderPaymentAdmin(admin.ModelAdmin):
    list_display = ("session_id", "order", "paid", "created_at")
    list_filter = ("paid",)
    search_fields = ("session_id",)

@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "percent_off", "active", "stripe_coupon_id")
    list_filter = ("active",)
    search_fields = ("name", "stripe_coupon_id")

@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "percentage", "inclusive", "active", "stripe_tax_rate_id")
    list_filter = ("active", "inclusive")
    search_fields = ("display_name", "stripe_tax_rate_id")
