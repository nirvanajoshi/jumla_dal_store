from orders.models import Cart


def cart_context(request):
    """Inject cart item count into every template context for the navbar badge."""
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            return {"cart_item_count": cart.items.count()}
        except Cart.DoesNotExist:
            pass
    return {"cart_item_count": 0}
