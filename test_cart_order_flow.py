"""
End-to-end test script for Cart → Order flow.
Run with:  python manage.py shell < test_cart_order_flow.py
"""
import os
import sys
import traceback
from decimal import Decimal
from io import StringIO

from django.db import transaction
from django.test.utils import setup_test_environment

# ── helpers ──────────────────────────────────────────────────────────────────
passed = []
failed = []

def check(label, condition, detail=""):
    if condition:
        passed.append(label)
        print(f"  ✅  {label}")
    else:
        failed.append(label)
        msg = f"  ❌  {label}"
        if detail:
            msg += f"  — {detail}"
        print(msg)


# ── 0. Setup: seed test data ────────────────────────────────────────────────
from accounts.models import User
from products.models import Product, Batch
from orders.models import Cart, CartItem, Order, OrderItem, create_order_from_cart

print("\n" + "=" * 70)
print("STEP 0 — Seed test data")
print("=" * 70)

# Get or create a test user
user, user_created = User.objects.get_or_create(
    username="test_farmer",
    defaults={"email": "testfarmer@example.com", "role": "FARMER"},
)
print(f"  User: {user.username} (created={user_created})")

# Create a product
product, prod_created = Product.objects.get_or_create(
    slug="test-buckwheat",
    defaults={"name": "Test Buckwheat", "description": "Test product", "is_active": True},
)
print(f"  Product: {product.name} (created={prod_created})")

# Create a batch with 50kg available
batch, batch_created = Batch.objects.get_or_create(
    product=product,
    source_village="Chandannath",
    defaults={
        "farmer_name": "Ram Bahadur",
        "harvest_date": "2026-08-15",
        "quantity_kg_total": Decimal("50.00"),
        "quantity_available": Decimal("50.00"),
        "price_per_kg": Decimal("120.00"),
        "is_active": True,
    },
)
print(f"  Batch: id={batch.id} avail={batch.quantity_available}kg @ Rs.{batch.price_per_kg}/kg (created={batch_created})")

# Refresh batch to get accurate state
batch.refresh_from_db()

# Clean up any prior test data
OrderItem.objects.filter(order__user=user).delete()
Order.objects.filter(user=user).delete()
CartItem.objects.filter(cart__user=user).delete()
Cart.objects.filter(user=user).delete()

print("  Cleaned prior test data for this user.")


# ── 1. Test: Cart auto-creation via signal ───────────────────────────────────
print("\n" + "=" * 70)
print("STEP 1 — Cart auto-creation (signal)")
print("=" * 70)

new_user, _ = User.objects.get_or_create(
    username="signal_test_user",
    defaults={"email": "signal@example.com"},
)
cart_exists = Cart.objects.filter(user=new_user).exists()
check("Cart auto-created for new user via post_save signal", cart_exists)

# Also ensure existing user can get/create a cart
cart, _ = Cart.objects.get_or_create(user=user)
check("Existing user can get_or_create a Cart", cart is not None, f"cart_id={cart.id}")


# ── 2. Test: add_item + totals ──────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2 — add_item + cart totals")
print("=" * 70)

item = cart.add_item(batch, Decimal("10.00"))
check("add_item returns a CartItem", isinstance(item, CartItem), f"item_id={item.id}")

cart.refresh_from_db()
expected_total = Decimal("10.00") * Decimal("120.00")
check(
    f"cart.total_price == {expected_total}",
    cart.total_price == expected_total,
    f"got {cart.total_price}",
)
check("cart.total_items == 1", cart.total_items == 1, f"got {cart.total_items}")

# Add same batch again → should increase quantity
item2 = cart.add_item(batch, Decimal("5.00"))
check(
    "Adding same batch again increases quantity (not duplicate)",
    CartItem.objects.filter(cart=cart, batch=batch).count() == 1,
)
item.refresh_from_db()
check(
    "Quantity increased to 15kg",
    item.quantity_kg == Decimal("15.00"),
    f"got {item.quantity_kg}",
)
expected_total_2 = Decimal("15.00") * Decimal("120.00")
check(
    f"cart.total_price updated to {expected_total_2}",
    cart.total_price == expected_total_2,
    f"got {cart.total_price}",
)
check("cart.total_items still == 1", cart.total_items == 1, f"got {cart.total_items}")


# ── 3. Test: create_order_from_cart (success) ────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3 — create_order_from_cart (success)")
print("=" * 70)

stock_before = batch.quantity_available
order = create_order_from_cart(
    cart,
    delivery_address="Test Street 123",
    delivery_city="Kathmandu",
    delivery_fee=Decimal("50.00"),
)
check("create_order_from_cart returns an Order", isinstance(order, Order), f"order_id={order.id}")

expected_grand_total = Decimal("15.00") * Decimal("120.00") + Decimal("50.00")  # 1850.00
check(
    f"order.grand_total == {expected_grand_total}",
    order.grand_total == expected_grand_total,
    f"got {order.grand_total}",
)
check("order.status == 'placed'", order.status == "placed", f"got {order.status}")
check("order.delivery_address correct", order.delivery_address == "Test Street 123")
check("order.delivery_city correct", order.delivery_city == "Kathmandu")


# ── 4. Test: cart cleared after order ────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 4 — Cart cleared after order")
print("=" * 70)

cart.refresh_from_db()
check("cart is now empty", cart.total_items == 0, f"got {cart.total_items} items")
check("cart.total_price == 0", cart.total_price == Decimal("0"), f"got {cart.total_price}")


# ── 5. Test: batch stock reduced ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 5 — Batch stock reduced")
print("=" * 70)

batch.refresh_from_db()
expected_stock = stock_before - Decimal("15.00")
check(
    f"batch.quantity_available == {expected_stock} (was {stock_before})",
    batch.quantity_available == expected_stock,
    f"got {batch.quantity_available}",
)


# ── 6. Test: OrderItem snapshot fields ───────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 6 — OrderItem snapshot fields")
print("=" * 70)

oi = OrderItem.objects.filter(order=order).first()
check("OrderItem exists for the order", oi is not None, f"oi_id={oi.id if oi else 'None'}")
if oi:
    check(
        f"product_name == {product.name!r}",
        oi.product_name == product.name,
        f"got {oi.product_name!r}",
    )
    check(
        f"source_village == {batch.source_village!r}",
        oi.source_village == batch.source_village,
        f"got {oi.source_village!r}",
    )
    check(
        "price_per_kg_at_order == 120.00 (snapshotted)",
        oi.price_per_kg_at_order == Decimal("120.00"),
        f"got {oi.price_per_kg_at_order}",
    )
    check(
        "quantity_kg == 15.00",
        oi.quantity_kg == Decimal("15.00"),
        f"got {oi.quantity_kg}",
    )
    check(
        "OrderItem.subtotal == 1800.00",
        oi.subtotal == Decimal("1800.00"),
        f"got {oi.subtotal}",
    )


# ── 7. Test: failure — add_item with exceeding quantity ──────────────────────
print("\n" + "=" * 70)
print("STEP 7 — Failure: add_item exceeds available stock")
print("=" * 70)

try:
    # batch has 35.00 kg available; try to add 36.00
    too_much = Decimal("36.00")
    cart.add_item(batch, too_much)
    check("add_item raised ValueError for excess quantity", False, "No exception raised!")
except ValueError as e:
    check(
        "add_item raises ValueError for excess quantity",
        True,
    )
    print(f"       Error message: {e}")
except Exception as e:
    check("add_item raises ValueError (not other exception)", False, f"Got {type(e).__name__}: {e}")


# ── 8. Test: failure — add_item to existing cart item exceeding stock ─────────
print("\n" + "=" * 70)
print("STEP 8 — Failure: add_item (cumulative) exceeds available stock")
print("=" * 70)

cart2, _ = Cart.objects.get_or_create(user=user)
cart2.add_item(batch, Decimal("30.00"))  # batch has 35.00 now

try:
    cart2.add_item(batch, Decimal("6.00"))  # would make 36.00, exceeding 35.00
    check("Cumulative add_item raises ValueError", False, "No exception raised!")
except ValueError as e:
    check("Cumulative add_item raises ValueError", True)
    print(f"       Error message: {e}")
except Exception as e:
    check("Cumulative add_item raises ValueError", False, f"Got {type(e).__name__}: {e}")

# Verify the cart item stayed at 30.00 (wasn't modified)
cart2_item = cart2.items.get(batch=batch)
check(
    "Cart item quantity unchanged after failed cumulative add",
    cart2_item.quantity_kg == Decimal("30.00"),
    f"got {cart2_item.quantity_kg}",
)


# ── 9. Test: atomicity — partial failure leaves nothing behind ───────────────
print("\n" + "=" * 70)
print("STEP 9 — Atomicity: partial stock failure commits nothing")
print("=" * 70)

# Create a second product + batch with very low stock
product2, _ = Product.objects.get_or_create(
    slug="test-maize",
    defaults={"name": "Test Maize", "is_active": True},
)
batch2, _ = Batch.objects.get_or_create(
    product=product2,
    source_village="Tatopani",
    defaults={
        "farmer_name": "Sita Devi",
        "harvest_date": "2026-08-20",
        "quantity_kg_total": Decimal("5.00"),
        "quantity_available": Decimal("5.00"),
        "price_per_kg": Decimal("80.00"),
        "is_active": True,
    },
)

# Refresh to get accurate stock
batch.refresh_from_db()
batch2.refresh_from_db()

cart3, _ = Cart.objects.get_or_create(user=user)
cart3.items.all().delete()  # start clean

# Add batch (35.00 available) with 20.00kg — this is fine
cart3.add_item(batch, Decimal("20.00"))
# Add batch2 (5.00 available) with 6.00kg — this will fail at checkout
cart3.add_item(batch2, Decimal("6.00"))

print(f"  Cart has {cart3.total_items} items, total={cart3.total_price}")

# Count orders and order items before
orders_before = Order.objects.filter(user=user).count()
items_before = OrderItem.objects.filter(order__user=user).count()
batch_stock_before = batch.quantity_available
batch2_stock_before = batch2.quantity_available

try:
    create_order_from_cart(cart3, delivery_address="Atomic Test", delivery_city="Kathmandu")
    check("create_order_from_cart raised ValueError for partial stock failure", False, "No exception!")
except ValueError as e:
    check("create_order_from_cart raised ValueError for partial stock failure", True)
    print(f"       Error message: {e}")
except Exception as e:
    check("create_order_from_cart raised error", False, f"Got {type(e).__name__}: {e}")

# Verify nothing was committed
orders_after = Order.objects.filter(user=user).count()
items_after = OrderItem.objects.filter(order__user=user).count()
batch.refresh_from_db()
batch2.refresh_from_db()

check(
    "No new Order rows created",
    orders_after == orders_before,
    f"before={orders_before}, after={orders_after}",
)
check(
    "No new OrderItem rows created",
    items_after == items_before,
    f"before={items_before}, after={items_after}",
)
check(
    "Batch1 stock unchanged",
    batch.quantity_available == batch_stock_before,
    f"before={batch_stock_before}, after={batch.quantity_available}",
)
check(
    "Batch2 stock unchanged",
    batch2.quantity_available == batch2_stock_before,
    f"before={batch2_stock_before}, after={batch2.quantity_available}",
)

# Verify cart still has items (cart.clear() was inside the atomic block, so it should be rolled back)
cart3.refresh_from_db()
check(
    "Cart still has items (rolled back)",
    cart3.total_items == 2,
    f"got {cart3.total_items}",
)


# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"\n  ✅  Passed: {len(passed)}")
for p in passed:
    print(f"      • {p}")
print(f"\n  ❌  Failed: {len(failed)}")
for f in failed:
    print(f"      • {f}")

if failed:
    print(f"\n  ⚠️  {len(failed)} test(s) FAILED — see details above.")
    sys.exit(1)
else:
    print("\n  🎉  All tests passed!")
