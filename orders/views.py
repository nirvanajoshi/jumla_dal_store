from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import transaction

from products.models import Batch
from .models import Cart, CartItem, Order, create_order_from_cart


@login_required
def cart_detail(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related("batch__product").all()
    return render(request, "orders/cart_detail.html", {
        "cart": cart,
        "cart_items": cart_items,
    })


@login_required
@require_POST
def add_to_cart(request):
    """HTMX endpoint: add a batch to the cart. Returns a batch card replacement."""
    batch_id = request.POST.get("batch_id")
    quantity_kg = request.POST.get("quantity_kg")

    if not batch_id or not quantity_kg:
        return HttpResponseBadRequest("Missing batch_id or quantity_kg")

    try:
        batch = Batch.objects.select_related("product").get(id=batch_id)
        qty = Decimal(quantity_kg)
    except (Batch.DoesNotExist, Exception) as e:
        return HttpResponseBadRequest(str(e))

    cart, _ = Cart.objects.get_or_create(user=request.user)

    try:
        cart.add_item(batch, qty)
    except ValueError as e:
        # Return an error message inside the batch card
        return render(request, "orders/_batch_error.html", {
            "batch": batch,
            "error": str(e),
        })

    # Return a success message inside the batch card
    return render(request, "orders/_batch_success.html", {"batch": batch})


@login_required
@require_POST
def update_cart_item(request, item_id):
    """HTMX endpoint: update quantity of a cart item."""
    cart = get_object_or_404(Cart, user=request.user)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    quantity_kg = request.POST.get("quantity_kg")

    if not quantity_kg:
        return HttpResponseBadRequest("Missing quantity_kg")

    try:
        qty = Decimal(quantity_kg)
        if qty <= 0:
            item.delete()
        else:
            cart.update_item_quantity(item.batch, qty)
    except ValueError as e:
        messages.error(request, str(e))

    # Return the full updated cart for HTMX swap
    cart.refresh_from_db()
    cart_items = cart.items.select_related("batch__product").all()
    return render(request, "orders/_cart_content.html", {
        "cart": cart,
        "cart_items": cart_items,
    })


@login_required
@require_POST
def remove_cart_item(request, item_id):
    """HTMX endpoint: remove an item from the cart."""
    cart = get_object_or_404(Cart, user=request.user)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    item.delete()

    cart.refresh_from_db()
    cart_items = cart.items.select_related("batch__product").all()
    return render(request, "orders/_cart_content.html", {
        "cart": cart,
        "cart_items": cart_items,
    })


@login_required
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user)
    cart_items = cart.items.select_related("batch__product").all()

    if not cart_items.exists():
        messages.warning(request, "Your cart is empty.")
        return redirect("products:product_list")

    if request.method == "POST":
        delivery_address = request.POST.get("delivery_address", "").strip()
        delivery_city = request.POST.get("delivery_city", "").strip()

        if not delivery_address or not delivery_city:
            messages.error(request, "Please fill in both delivery address and city.")
            return render(request, "orders/checkout.html", {
                "cart": cart,
                "cart_items": cart_items,
            })

        try:
            order = create_order_from_cart(
                cart,
                delivery_address=delivery_address,
                delivery_city=delivery_city,
            )
            messages.success(request, f"Order #{order.id} placed successfully!")
            return redirect("orders:order_confirmation", order_id=order.id)
        except ValueError as e:
            messages.error(request, str(e))
            return render(request, "orders/checkout.html", {
                "cart": cart,
                "cart_items": cart_items,
            })

    return render(request, "orders/checkout.html", {
        "cart": cart,
        "cart_items": cart_items,
    })


@login_required
def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "orders/order_confirmation.html", {"order": order})
