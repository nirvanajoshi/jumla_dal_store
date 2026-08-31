from django.db import models
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