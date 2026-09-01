from django.contrib import admin
from .models import Cart, CartItem, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_name', 'source_village', 'quantity_kg', 'price_per_kg_at_order')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'delivery_city', 'grand_total', 'placed_at')
    list_filter = ('status', 'delivery_city')
    inlines = [OrderItemInline]
    readonly_fields = ('placed_at', 'updated_at')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')