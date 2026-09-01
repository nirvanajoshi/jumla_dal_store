from django.db import models
from django.conf import settings


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def available_batches(self):
        return self.batches.filter(quantity_available__gt=0, is_active=True)

    @property
    def total_stock_kg(self):
        return sum(b.quantity_available for b in self.available_batches)

    @property
    def starting_price(self):
        cheapest = self.available_batches.order_by('price_per_kg').first()
        return cheapest.price_per_kg if cheapest else None


class Batch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    source_village = models.CharField(max_length=150, help_text="e.g. Chandannath, Jumla")
    farmer_name = models.CharField(max_length=150, blank=True)
    harvest_date = models.DateField()
    quantity_kg_total = models.DecimalField(max_digits=8, decimal_places=2)
    quantity_available = models.DecimalField(max_digits=8, decimal_places=2)
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['harvest_date']
        verbose_name_plural = 'Batches'

    def __str__(self):
        return f"{self.product.name} - {self.source_village} ({self.harvest_date})"

    def reduce_stock(self, quantity_kg):
        """Reduce available stock when an order is placed. Raises if insufficient."""
        if quantity_kg > self.quantity_available:
            raise ValueError("Not enough stock in this batch.")
        self.quantity_available -= quantity_kg
        self.save(update_fields=['quantity_available'])