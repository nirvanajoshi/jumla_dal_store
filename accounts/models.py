from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom User model for the Jumla Dal store."""

    class Role(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        FARMER = 'FARMER', 'Farmer'
        ADMIN = 'ADMIN', 'Admin'

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"