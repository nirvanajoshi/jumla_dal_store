from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/", views.add_to_cart, name="add_to_cart"),
    path("cart/item/<int:item_id>/update/", views.update_cart_item, name="update_cart_item"),
    path("cart/item/<int:item_id>/remove/", views.remove_cart_item, name="remove_cart_item"),
    path("checkout/", views.checkout, name="checkout"),
    path("order/<int:order_id>/", views.order_confirmation, name="order_confirmation"),
]
