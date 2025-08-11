from django.contrib import admin
from .models import Item, CheckoutSession

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "price", "currency")
    list_filter = ("currency",)
    search_fields = ("name",)

@admin.register(CheckoutSession)
class CheckoutSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id", "item", "paid", "created_at")
    list_filter = ("paid", "item__currency")
    search_fields = ("session_id", "item__name")
