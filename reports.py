class Reports:
    def __init__(self, conn):
        self.conn = conn

    def status_breakdown(self):
        return {r["status"]: r["n"] for r in self.conn.execute(
            "SELECT status, COUNT(*) n FROM orders GROUP BY status ORDER BY n DESC, status")}

    def revenue_cents(self):
        """Net revenue = successful payments that were not refunded."""
        return self.conn.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE status='SUCCEEDED'").fetchone()[0]

    def refunded_cents(self):
        return self.conn.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE status='REFUNDED'").fetchone()[0]

    def avg_fulfilment_seconds(self):
        """Average time from OrderCreated to OrderDelivered."""
        return self.conn.execute("""
          SELECT AVG((julianday(d.ts)-julianday(c.ts))*86400.0)
          FROM events c JOIN events d ON c.order_id=d.order_id
          WHERE c.type='OrderCreated' AND d.type='OrderDelivered'""").fetchone()[0]

    def top_products(self, n=3):
        return [dict(r) for r in self.conn.execute("""
          SELECT p.name, SUM(oi.qty) units FROM order_items oi
          JOIN orders o ON o.id=oi.order_id JOIN products p ON p.sku=oi.sku
          WHERE o.status IN ('SHIPPED','OUT_FOR_DELIVERY','DELIVERED')
          GROUP BY p.sku ORDER BY units DESC LIMIT ?""", (n,))]
