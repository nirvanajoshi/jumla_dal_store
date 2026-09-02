from django.shortcuts import render
from products.models import Product


def home(request):
    featured_products = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .prefetch_related("batches")
        .order_by("-created_at")[:4]
    )
    return render(request, "core_pages/home.html", {"featured_products": featured_products})
