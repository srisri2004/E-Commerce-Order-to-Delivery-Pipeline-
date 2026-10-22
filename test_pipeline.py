import unittest

from ecom.models import InvalidTransition, OrderStatus as S, ValidationError
from ecom.orchestrator import OrderPipeline
from ecom.reports import Reports


def stock(p, sku):
    r = p.conn.execute("SELECT stock, reserved FROM products WHERE sku=?", (sku,)).fetchone()
    return r["stock"], r["reserved"]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.p = OrderPipeline()
        self.p.inventory.add_product("A", "Item A", 1000, 10)
        self.p.inventory.add_product("B", "Item B", 500, 1)

    def order(self, items, token="tok_ok", key=None):
        return self.p.place_order("Test", "t@example.com",
                                  [{"sku": s, "qty": q} for s, q in items], token, key)

    def test_happy_path_to_delivery(self):
        oid = self.order([("A", 2)])
        self.assertEqual(self.p.run_to_delivery(oid), S.DELIVERED)
        self.assertEqual(stock(self.p, "A"), (8, 0))
        self.assertEqual(self.p.shipping.get(oid)["status"], "DELIVERED")
        types = [t for _, t, _ in self.p.bus.timeline(oid)]
        self.assertEqual(types, ["OrderCreated", "InventoryReserved", "PaymentSucceeded",
                                 "OrderPacked", "OrderShipped", "OrderOutForDelivery",
                                 "OrderDelivered"])

    def test_total_and_duplicate_sku_merge(self):
        oid = self.order([("A", 1), ("A", 2), ("B", 1)])
        self.assertEqual(self.p.get_order(oid)["total_cents"], 3 * 1000 + 500)

    def test_out_of_stock_rolls_back_partial_reservation(self):
        oid = self.order([("A", 3), ("B", 2)])     # B only has 1
        self.assertEqual(self.p.process(oid), S.OUT_OF_STOCK)
        self.assertEqual(stock(self.p, "A"), (10, 0))   # A's reservation undone
        self.assertEqual(stock(self.p, "B"), (1, 0))

    def test_payment_failure_releases_stock(self):
        oid = self.order([("A", 4)], token="tok_fail")
        self.assertEqual(self.p.process(oid), S.PAYMENT_FAILED)
        self.assertEqual(stock(self.p, "A"), (10, 0))
        self.assertEqual(Reports(self.p.conn).revenue_cents(), 0)

    def test_cancel_after_payment_refunds_and_releases(self):
        oid = self.order([("A", 2)])
        self.assertEqual(self.p.process(oid, auto_ship=False), S.PAID)
        self.assertEqual(stock(self.p, "A"), (10, 2))
        self.p.cancel(oid)
        self.assertEqual(self.p.get_order(oid)["status"], "CANCELLED")
        self.assertEqual(stock(self.p, "A"), (10, 0))
        rep = Reports(self.p.conn)
        self.assertEqual((rep.revenue_cents(), rep.refunded_cents()), (0, 2000))

    def test_cannot_cancel_after_shipping(self):
        oid = self.order([("A", 1)])
        self.p.process(oid)
        with self.assertRaises(InvalidTransition):
            self.p.cancel(oid)

    def test_illegal_transitions_rejected(self):
        oid = self.order([("A", 1)])
        with self.assertRaises(InvalidTransition):
            self.p.mark_delivered(oid)              # CREATED -> DELIVERED
        self.p.process(oid)
        with self.assertRaises(InvalidTransition):
            self.p.process(oid)                     # double-processing

    def test_idempotency_key_prevents_duplicates(self):
        a = self.order([("A", 1)], key="k1")
        b = self.order([("A", 1)], key="k1")
        self.assertEqual(a, b)
        self.assertEqual(sum(Reports(self.p.conn).status_breakdown().values()), 1)

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self.order([])
        with self.assertRaises(ValidationError):
            self.order([("A", 0)])
        with self.assertRaises(ValidationError):
            self.order([("NOPE", 1)])
        with self.assertRaises(ValidationError):
            self.p.place_order("x", "bad-email", [{"sku": "A", "qty": 1}], "tok_ok")

    def test_no_overselling_across_orders(self):
        o1, o2 = self.order([("B", 1)]), self.order([("B", 1)])
        self.assertEqual(self.p.process(o1), S.SHIPPED)
        self.assertEqual(self.p.process(o2), S.OUT_OF_STOCK)

    def test_notifications_sent(self):
        oid = self.order([("A", 1)])
        self.p.run_to_delivery(oid)
        bodies = [b for _, b in self.p.notifier.outbox]
        self.assertTrue(any("shipped via" in b for b in bodies))
        self.assertTrue(any("delivered" in b for b in bodies))

    def test_reports(self):
        self.p.run_to_delivery(self.order([("A", 2)]))
        rep = Reports(self.p.conn)
        self.assertEqual(rep.status_breakdown(), {"DELIVERED": 1})
        self.assertEqual(rep.revenue_cents(), 2000)
        self.assertEqual(rep.top_products()[0]["units"], 2)
        self.assertIsNotNone(rep.avg_fulfilment_seconds())


if __name__ == "__main__":
    unittest.main()
