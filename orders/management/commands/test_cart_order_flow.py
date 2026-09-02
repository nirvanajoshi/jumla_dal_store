"""
Management command: test_cart_order_flow
Runs end-to-end verification of Cart, Order, and atomicity logic.

Usage:
    python manage.py test_cart_order_flow
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from products.models import Product, Batch
from orders.models import Cart, CartItem, Order, OrderItem, create_order_from_cart


class Command(BaseCommand):
    help = "End-to-end test of Cart-to-Order flow"

    def handle(self, *args, **options):
        self.passed = []
        self.failed = []

        self.step0_seed_data()
        self.step1_cart_signal()
        self.step2_add_item_and_totals()
        self.step3_create_order_success()
        self.step4_cart_cleared()
        self.step5_batch_stock_reduced()
        self.step6_orderitem_snapshots()
        self.step7_fail_exceed_quantity()
        self.step8_fail_cumulative_exceed()
        self.step9_atomicity_partial_failure()

        self.summary()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def verify(self, label, condition, detail=""):
        if condition:
            self.passed.append(label)
            self.stdout.write(self.style.SUCCESS(f"  PASS  {label}"))
        else:
            self.failed.append(label)
            msg = f"  FAIL  {label}"
            if detail:
                msg += f"  -- {detail}"
            self.stdout.write(self.style.ERROR(msg))

    # ------------------------------------------------------------------
    # Step 0: Seed test data
    # ------------------------------------------------------------------
    def step0_seed_data(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 0 -- Seed test data")
        self.stdout.write("=" * 70)

        self.user, created = User.objects.get_or_create(
            username="test_farmer",
            defaults={"email": "testfarmer@example.com", "role": "FARMER"},
        )
        self.stdout.write(f"  User: {self.user.username} (created={created})")

        self.product, _ = Product.objects.get_or_create(
            slug="test-buckwheat",
            defaults={"name": "Test Buckwheat", "description": "Test product", "is_active": True},
        )
        self.stdout.write(f"  Product: {self.product.name}")

        self.batch, batch_created = Batch.objects.get_or_create(
            product=self.product,
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
        self.stdout.write(f"  Batch: id={self.batch.id} avail={self.batch.quantity_available}kg @ Rs.{self.batch.price_per_kg}/kg")

        self.batch.refresh_from_db()
        # Reset batch stock to a known state (previous run may have consumed it)
        if self.batch.quantity_available != Decimal("50.00"):
            self.batch.quantity_available = Decimal("50.00")
            self.batch.save(update_fields=["quantity_available"])
            self.stdout.write(f"  Reset batch stock to 50.00kg")

        # Clean prior test data
        OrderItem.objects.filter(order__user=self.user).delete()
        Order.objects.filter(user=self.user).delete()
        CartItem.objects.filter(cart__user=self.user).delete()
        Cart.objects.filter(user=self.user).delete()
        self.stdout.write("  Cleaned prior test data for this user.")

    # ------------------------------------------------------------------
    # Step 1: Cart auto-creation via signal
    # ------------------------------------------------------------------
    def step1_cart_signal(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 1 -- Cart auto-creation (signal)")
        self.stdout.write("=" * 70)

        new_user, _ = User.objects.get_or_create(
            username="signal_test_user",
            defaults={"email": "signal@example.com"},
        )
        cart_exists = Cart.objects.filter(user=new_user).exists()
        self.verify("Cart auto-created for new user via post_save signal", cart_exists)

        # Existing user can get_or_create a cart
        cart, _ = Cart.objects.get_or_create(user=self.user)
        self.verify("Existing user can get_or_create a Cart", cart is not None, f"cart_id={cart.id}")

    # ------------------------------------------------------------------
    # Step 2: add_item + cart totals
    # ------------------------------------------------------------------
    def step2_add_item_and_totals(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 2 -- add_item + cart totals")
        self.stdout.write("=" * 70)

        cart, _ = Cart.objects.get_or_create(user=self.user)
        # clear any leftovers
        cart.items.all().delete()

        # Add 10 kg
        item = cart.add_item(self.batch, Decimal("10.00"))
        self.verify("add_item returns a CartItem", isinstance(item, CartItem), f"item_id={item.id}")

        cart.refresh_from_db()
        expected_total = Decimal("10.00") * Decimal("120.00")
        self.verify(
            f"cart.total_price == {expected_total}",
            cart.total_price == expected_total,
            f"got {cart.total_price}",
        )
        self.verify("cart.total_items == 1", cart.total_items == 1, f"got {cart.total_items}")

        # Add same batch again -> should increase quantity, not duplicate
        item2 = cart.add_item(self.batch, Decimal("5.00"))
        self.verify(
            "Adding same batch increases quantity (no duplicate)",
            CartItem.objects.filter(cart=cart, batch=self.batch).count() == 1,
        )
        item.refresh_from_db()
        self.verify(
            "Quantity increased to 15kg",
            item.quantity_kg == Decimal("15.00"),
            f"got {item.quantity_kg}",
        )
        expected_total_2 = Decimal("15.00") * Decimal("120.00")
        self.verify(
            f"cart.total_price updated to {expected_total_2}",
            cart.total_price == expected_total_2,
            f"got {cart.total_price}",
        )
        self.verify("cart.total_items still == 1", cart.total_items == 1, f"got {cart.total_items}")

    # ------------------------------------------------------------------
    # Step 3: create_order_from_cart (success)
    # ------------------------------------------------------------------
    def step3_create_order_success(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 3 -- create_order_from_cart (success)")
        self.stdout.write("=" * 70)

        cart, _ = Cart.objects.get_or_create(user=self.user)
        self.batch.refresh_from_db()
        self.stock_before = self.batch.quantity_available

        order = create_order_from_cart(
            cart,
            delivery_address="Test Street 123",
            delivery_city="Kathmandu",
            delivery_fee=Decimal("50.00"),
        )
        self.order = order
        self.verify("create_order_from_cart returns an Order", isinstance(order, Order), f"order_id={order.id}")

        expected_grand_total = Decimal("15.00") * Decimal("120.00") + Decimal("50.00")  # 1850.00
        self.verify(
            f"order.grand_total == {expected_grand_total}",
            order.grand_total == expected_grand_total,
            f"got {order.grand_total}",
        )
        self.verify("order.status == 'placed'", order.status == "placed", f"got {order.status}")
        self.verify("order.delivery_address correct", order.delivery_address == "Test Street 123")
        self.verify("order.delivery_city correct", order.delivery_city == "Kathmandu")

    # ------------------------------------------------------------------
    # Step 4: cart cleared after order
    # ------------------------------------------------------------------
    def step4_cart_cleared(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 4 -- Cart cleared after order")
        self.stdout.write("=" * 70)

        cart, _ = Cart.objects.get_or_create(user=self.user)
        cart.refresh_from_db()
        self.verify("cart is now empty", cart.total_items == 0, f"got {cart.total_items} items")
        self.verify("cart.total_price == 0", cart.total_price == Decimal("0"), f"got {cart.total_price}")

    # ------------------------------------------------------------------
    # Step 5: batch stock reduced
    # ------------------------------------------------------------------
    def step5_batch_stock_reduced(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 5 -- Batch stock reduced")
        self.stdout.write("=" * 70)

        self.batch.refresh_from_db()
        expected_stock = self.stock_before - Decimal("15.00")
        self.verify(
            f"batch.quantity_available == {expected_stock} (was {self.stock_before})",
            self.batch.quantity_available == expected_stock,
            f"got {self.batch.quantity_available}",
        )

    # ------------------------------------------------------------------
    # Step 6: OrderItem snapshot fields
    # ------------------------------------------------------------------
    def step6_orderitem_snapshots(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 6 -- OrderItem snapshot fields")
        self.stdout.write("=" * 70)

        oi = OrderItem.objects.filter(order=self.order).first()
        self.verify("OrderItem exists for the order", oi is not None, f"oi_id={oi.id if oi else 'None'}")
        if oi:
            self.verify(
                f"product_name == {self.product.name!r}",
                oi.product_name == self.product.name,
                f"got {oi.product_name!r}",
            )
            self.verify(
                f"source_village == {self.batch.source_village!r}",
                oi.source_village == self.batch.source_village,
                f"got {oi.source_village!r}",
            )
            self.verify(
                "price_per_kg_at_order == 120.00 (snapshotted)",
                oi.price_per_kg_at_order == Decimal("120.00"),
                f"got {oi.price_per_kg_at_order}",
            )
            self.verify(
                "quantity_kg == 15.00",
                oi.quantity_kg == Decimal("15.00"),
                f"got {oi.quantity_kg}",
            )
            self.verify(
                "OrderItem.subtotal == 1800.00",
                oi.subtotal == Decimal("1800.00"),
                f"got {oi.subtotal}",
            )

    # ------------------------------------------------------------------
    # Step 7: failure -- add_item exceeds available stock
    # ------------------------------------------------------------------
    def step7_fail_exceed_quantity(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 7 -- Failure: add_item exceeds available stock")
        self.stdout.write("=" * 70)

        cart, _ = Cart.objects.get_or_create(user=self.user)
        cart.items.all().delete()
        self.batch.refresh_from_db()

        try:
            cart.add_item(self.batch, Decimal("36.00"))
            self.verify("add_item raised ValueError for excess quantity", False, "No exception raised!")
        except ValueError as e:
            self.verify("add_item raises ValueError for excess quantity", True)
            self.stdout.write(f"       Error message: {e}")
        except Exception as e:
            self.verify("add_item raises ValueError (not other exception)", False, f"Got {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    # Step 8: failure -- cumulative add exceeds stock
    # ------------------------------------------------------------------
    def step8_fail_cumulative_exceed(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 8 -- Failure: cumulative add_item exceeds available stock")
        self.stdout.write("=" * 70)

        self.batch.refresh_from_db()
        cart2, _ = Cart.objects.get_or_create(user=self.user)
        cart2.items.all().delete()
        cart2.add_item(self.batch, Decimal("30.00"))

        try:
            cart2.add_item(self.batch, Decimal("6.00"))  # would make 36 > 35 available
            self.verify("Cumulative add_item raises ValueError", False, "No exception raised!")
        except ValueError as e:
            self.verify("Cumulative add_item raises ValueError", True)
            self.stdout.write(f"       Error message: {e}")
        except Exception as e:
            self.verify("Cumulative add_item raises ValueError", False, f"Got {type(e).__name__}: {e}")

        cart2_item = cart2.items.get(batch=self.batch)
        self.verify(
            "Cart item quantity unchanged after failed cumulative add",
            cart2_item.quantity_kg == Decimal("30.00"),
            f"got {cart2_item.quantity_kg}",
        )

    # ------------------------------------------------------------------
    # Step 9: atomicity -- partial failure commits nothing
    # ------------------------------------------------------------------
    def step9_atomicity_partial_failure(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("STEP 9 -- Atomicity: partial stock failure commits nothing")
        self.stdout.write("=" * 70)

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

        self.batch.refresh_from_db()
        batch2.refresh_from_db()

        cart3, _ = Cart.objects.get_or_create(user=self.user)
        cart3.items.all().delete()

        # Add items that are initially valid (within stock)
        cart3.add_item(self.batch, Decimal("20.00"))   # batch has 35kg -> OK
        cart3.add_item(batch2, Decimal("4.00"))        # batch2 has 5kg -> OK

        # Simulate a race condition: another user buys stock from batch2
        # before this user checks out. Reduce stock to 2kg so our 4kg will fail.
        batch2.refresh_from_db()
        batch2.quantity_available = Decimal("2.00")
        batch2.save(update_fields=["quantity_available"])

        self.stdout.write(f"  Cart has {cart3.total_items} item(s), total={cart3.total_price}")

        # Take snapshots before the attempt
        orders_before = Order.objects.filter(user=self.user).count()
        items_before = OrderItem.objects.filter(order__user=self.user).count()
        batch_stock_before = self.batch.quantity_available
        batch2_stock_before = batch2.quantity_available

        try:
            create_order_from_cart(cart3, delivery_address="Atomic Test", delivery_city="Kathmandu")
            self.verify("create_order_from_cart raised ValueError for partial stock", False, "No exception!")
        except ValueError as e:
            self.verify("create_order_from_cart raised ValueError for partial stock", True)
            self.stdout.write(f"       Error message: {e}")
        except Exception as e:
            self.verify("create_order_from_cart raised error", False, f"Got {type(e).__name__}: {e}")

        # Verify nothing was committed (atomic rollback)
        orders_after = Order.objects.filter(user=self.user).count()
        items_after = OrderItem.objects.filter(order__user=self.user).count()
        self.batch.refresh_from_db()
        batch2.refresh_from_db()

        self.verify(
            "No new Order rows created",
            orders_after == orders_before,
            f"before={orders_before}, after={orders_after}",
        )
        self.verify(
            "No new OrderItem rows created",
            items_after == items_before,
            f"before={items_before}, after={items_after}",
        )
        self.verify(
            "Batch1 stock unchanged",
            self.batch.quantity_available == batch_stock_before,
            f"before={batch_stock_before}, after={self.batch.quantity_available}",
        )
        self.verify(
            "Batch2 stock unchanged",
            batch2.quantity_available == batch2_stock_before,
            f"before={batch2_stock_before}, after={batch2.quantity_available}",
        )

        cart3.refresh_from_db()
        self.verify(
            "Cart still has items (rolled back)",
            cart3.total_items == 2,
            f"got {cart3.total_items}",
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def summary(self):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 70)
        self.stdout.write("")
        self.stdout.write(f"  Passed: {len(self.passed)}")
        for p in self.passed:
            self.stdout.write(f"    * {p}")
        self.stdout.write("")
        self.stdout.write(f"  Failed: {len(self.failed)}")
        for f in self.failed:
            self.stdout.write(f"    * {f}")

        if self.failed:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"  {len(self.failed)} test(s) FAILED -- see details above."))
        else:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("  ALL TESTS PASSED!"))
