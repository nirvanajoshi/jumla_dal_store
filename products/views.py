from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse

from .models import Product, Category


def product_list(request):
    """Product listing with optional HTMX category filter."""
    category_slug = request.GET.get("category", "")
    search_query = request.GET.get("q", "").strip()
    products = Product.objects.filter(is_active=True).select_related("category").prefetch_related("batches")
    categories = Category.objects.all()

    if category_slug:
        products = products.filter(category__slug=category_slug)
    if search_query:
        products = products.filter(name__icontains=search_query)

    # If this is an HTMX request, return only the product grid partial
    if request.headers.get("HX-Request"):
        return render(request, "products/_product_grid.html", {"products": products})

    return render(request, "products/product_list.html", {
        "products": products,
        "categories": categories,
        "active_category": category_slug,
        "search_query": search_query,
    })


def product_detail(request, slug):
    """Product detail with batch listing and HTMX add-to-cart."""
    product = get_object_or_404(
        Product.objects.select_related("category"),
        slug=slug,
        is_active=True,
    )
    batches = product.batches.filter(is_active=True).order_by("-harvest_date")

    return render(request, "products/product_detail.html", {
        "product": product,
        "batches": batches,
    })
