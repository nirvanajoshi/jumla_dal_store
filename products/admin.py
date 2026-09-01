from django.contrib import admin
from .models import Category, Product, Batch


class BatchInline(admin.TabularInline):
    model = Batch
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'total_stock_kg', 'starting_price')
    list_filter = ('category', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [BatchInline]


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('product', 'source_village', 'harvest_date', 'quantity_available', 'price_per_kg', 'is_active')
    list_filter = ('source_village', 'is_active')
    ordering = ('-harvest_date',)