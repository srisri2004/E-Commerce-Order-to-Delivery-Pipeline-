"""Saga orchestrator: drives an order from placement to delivery, compensating on failure."""
from .db import connect
from .events import EventBus
from .models import (CANCELLABLE, TRANSITIONS, InvalidTransition, OrderStatus as S,
                     ValidationError)
from .services.inventory import InventoryService
from .services.notification import NotificationService
from .services.payment import PaymentService
from .services.shipping import ShippingService


class OrderPipeline:
    def __init__(self, conn=None, gateway=None):
        self.conn = conn or connect()
        self.bus = EventBus(self.conn)
        self.inventory = InventoryService(self.conn)
        self.payments = PaymentService(self.conn, gateway)
        self.shipping = ShippingService(self.conn)
        self.notifier = NotificationService(self.conn)
        self.bus.subscribe("*", self.notifier.handle)

    # ---------- helpers ----------
    def get_order(self, order_id):
        row = self.conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise ValidationError(f"Order {order_id} not found")
        return dict(row)

    def _items(self, order_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT sku, qty, price_cents FROM order_items WHERE order_id=?", (order_id,))]

    def _set_status(self, order_id, new):
        cur = S(self.get_order(order_id)["status"])
        if new not in TRANSITIONS[cur]:
            raise InvalidTransition(f"Order {order_id}: {cur.value} -> {new.value} not allowed")
        self.conn.execute(
            "UPDATE orders SET status=?, updated_at=datetime('now') WHERE id=?", (new.value, order_id))

    # ---------- step 1: place ----------
    def place_order(self, customer, email, items, payment_token, idempotency_key=None):
        if not items:
            raise ValidationError("Order must contain at least one item")
        if any(i["qty"] <= 0 for i in items):
            raise ValidationError("Quantities must be positive")
        if "@" not in email:
            raise ValidationError("Invalid email")
        if idempotency_key:
            dup = self.conn.execute(
                "SELECT id FROM orders WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if dup:
                return dup["id"]
        with self.conn:
            merged = {}
            for i in items:                      # merge duplicate SKUs
                merged[i["sku"]] = merged.get(i["sku"], 0) + i["qty"]
            priced = [{"sku": s, "qty": q, "price_cents": self.inventory.get_price(s)}
                      for s, q in merged.items()]
            total = sum(i["qty"] * i["price_cents"] for i in priced)
            cur = self.conn.execute(
                "INSERT INTO orders(idempotency_key,customer,email,status,total_cents,payment_token)"
                " VALUES (?,?,?,?,?,?)",
                (idempotency_key, customer, email, S.CREATED.value, total, payment_token))
            oid = cur.lastrowid
            self.conn.executemany(
                "INSERT INTO order_items(order_id,sku,qty,price_cents) VALUES (?,?,?,?)",
                [(oid, i["sku"], i["qty"], i["price_cents"]) for i in priced])
            self.bus.publish("OrderCreated", oid, total_cents=total)
        return oid

    # ---------- steps 2-5: fulfilment saga ----------
    def process(self, order_id, auto_ship=True):
        """Reserve stock -> charge -> pack -> ship. Compensates on failure.
        With auto_ship=False the saga pauses after payment (order stays PAID)."""
        order, items = self.get_order(order_id), self._items(order_id)
        if S(order["status"]) != S.CREATED:
            raise InvalidTransition(f"Order {order_id} already processed ({order['status']})")

        with self.conn:                                   # 1. reserve inventory
            short = self.inventory.reserve(items)
            if short:
                self._set_status(order_id, S.OUT_OF_STOCK)
                self.bus.publish("OrderOutOfStock", order_id, skus=short)
                return S.OUT_OF_STOCK
            self._set_status(order_id, S.INVENTORY_RESERVED)
            self.bus.publish("InventoryReserved", order_id)

        with self.conn:                                   # 2. charge payment
            ok, ref, err = self.payments.charge(order_id, order["payment_token"], order["total_cents"])
            if not ok:
                self.inventory.release(items)             # compensation
                self._set_status(order_id, S.PAYMENT_FAILED)
                self.bus.publish("PaymentFailed", order_id, reason=err)
                return S.PAYMENT_FAILED
            self._set_status(order_id, S.PAID)
            self.bus.publish("PaymentSucceeded", order_id, txn_ref=ref)

        if not auto_ship:
            return S.PAID

        with self.conn:                                   # 3. pack + ship
            self._set_status(order_id, S.PACKED)
            self.bus.publish("OrderPacked", order_id)
            carrier, tracking = self.shipping.create_shipment(order_id)
            self.inventory.commit(items)                  # stock physically leaves
            self._set_status(order_id, S.SHIPPED)
            self.bus.publish("OrderShipped", order_id, carrier=carrier, tracking=tracking)
        return S.SHIPPED

    # ---------- carrier webhooks ----------
    def mark_out_for_delivery(self, order_id):
        with self.conn:
            self._set_status(order_id, S.OUT_FOR_DELIVERY)
            self.shipping.update(order_id, "OUT_FOR_DELIVERY")
            self.bus.publish("OrderOutForDelivery", order_id)

    def mark_delivered(self, order_id):
        with self.conn:
            self._set_status(order_id, S.DELIVERED)
            self.shipping.update(order_id, "DELIVERED")
            self.bus.publish("OrderDelivered", order_id)

    # ---------- cancellation with compensation ----------
    def cancel(self, order_id):
        with self.conn:
            status = S(self.get_order(order_id)["status"])
            if status not in CANCELLABLE:
                raise InvalidTransition(f"Cannot cancel order in {status.value}")
            if status != S.CREATED:                       # stock was reserved
                self.inventory.release(self._items(order_id))
            refunded = self.payments.refund(order_id)
            self._set_status(order_id, S.CANCELLED)
            self.bus.publish("OrderCancelled", order_id, refunded=refunded)

    # ---------- convenience ----------
    def run_to_delivery(self, order_id):
        if self.process(order_id) == S.SHIPPED:
            self.mark_out_for_delivery(order_id)
            self.mark_delivered(order_id)
        return S(self.get_order(order_id)["status"])
