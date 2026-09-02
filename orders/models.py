from django.db import models, transaction
from django.conf import settings
from products.models import Batch


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart - {self.user.username}"

    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def total_items(self):
        return self.items.count()

    def add_item(self, batch, quantity_kg):
        """Add a batch to cart, or increase quantity if it's already in cart."""
        if quantity_kg <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if quantity_kg > batch.quantity_available:
            raise ValueError(f"Only {batch.quantity_available}kg available in this batch.")

        item, created = self.items.get_or_create(
            batch=batch,
            defaults={'quantity_kg': quantity_kg}
        )
        if not created:
            new_quantity = item.quantity_kg + quantity_kg
            if new_quantity > batch.quantity_available:
                raise ValueError(f"Only {batch.quantity_available}kg available in this batch.")
            item.quantity_kg = new_quantity
            item.save(update_fields=['quantity_kg'])
        return item

    def update_item_quantity(self, batch, quantity_kg):
        """Set an item's quantity directly (used for +/- controls in UI)."""
        if quantity_kg <= 0:
            self.remove_item(batch)
            return None
        if quantity_kg > batch.quantity_available:
            raise ValueError(f"Only {batch.quantity_available}kg available in this batch.")

        item = self.items.get(batch=batch)
        item.quantity_kg = quantity_kg
        item.save(update_fields=['quantity_kg'])
        return item

    def remove_item(self, batch):
        self.items.filter(batch=batch).delete()

    def clear(self):
        self.items.all().delete()


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE)
    quantity_kg = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        unique_together = ('cart', 'batch')

    @property
    def subtotal(self):
        return self.quantity_kg * self.batch.price_per_kg

    def __str__(self):
        return f"{self.quantity_kg}kg of {self.batch.product.name}"


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = 'placed', 'Placed'
        PACKED = 'packed', 'Packed'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)
    delivery_address = models.TextField()
    delivery_city = models.CharField(max_length=100)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} - {self.user.username} - {self.status}"

    @property
    def items_total(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def grand_total(self):
        return self.items_total + self.delivery_fee


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True)

    # Snapshotted fields - important! Never rely on live Batch/Product data for historical orders
    product_name = models.CharField(max_length=200)
    source_village = models.CharField(max_length=150)
    quantity_kg = models.DecimalField(max_digits=6, decimal_places=2)
    price_per_kg_at_order = models.DecimalField(max_digits=8, decimal_places=2)

    @property
    def subtotal(self):
        return self.quantity_kg * self.price_per_kg_at_order

    def __str__(self):
        return f"{self.quantity_kg}kg {self.product_name}"


def create_order_from_cart(cart, delivery_address, delivery_city, delivery_fee=0):
    """
    Converts a Cart into an Order, snapshotting prices and reducing batch stock.
    Wrapped in a transaction: if anything fails, nothing is committed.
    """
    if not cart.items.exists():
        raise ValueError("Cannot create an order from an empty cart.")

    with transaction.atomic():
        order = Order.objects.create(
            user=cart.user,
            delivery_address=delivery_address,
            delivery_city=delivery_city,
            delivery_fee=delivery_fee,
        )

        for cart_item in cart.items.select_related('batch__product').all():
            batch = cart_item.batch

            # Re-check stock at the moment of checkout (it may have changed since adding to cart)
            if cart_item.quantity_kg > batch.quantity_available:
                raise ValueError(
                    f"Not enough stock for {batch.product.name} ({batch.source_village}). "
                    f"Only {batch.quantity_available}kg left."
                )

            OrderItem.objects.create(
                order=order,
                batch=batch,
                product_name=batch.product.name,
                source_village=batch.source_village,
                quantity_kg=cart_item.quantity_kg,
                price_per_kg_at_order=batch.price_per_kg,
            )

            batch.reduce_stock(cart_item.quantity_kg)

        cart.clear()

    return order