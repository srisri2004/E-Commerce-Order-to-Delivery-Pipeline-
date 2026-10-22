from ..models import ValidationError


class InventoryService:
    def __init__(self, conn):
        self.conn = conn

    def add_product(self, sku, name, price_cents, stock):
        self.conn.execute(
            "INSERT OR REPLACE INTO products(sku,name,price_cents,stock,reserved) VALUES (?,?,?,?,0)",
            (sku, name, price_cents, stock),
        )
        self.conn.commit()

    def get_price(self, sku):
        row = self.conn.execute("SELECT price_cents FROM products WHERE sku=?", (sku,)).fetchone()
        if not row:
            raise ValidationError(f"Unknown SKU: {sku}")
        return row["price_cents"]

    def available(self, sku):
        r = self.conn.execute("SELECT stock-reserved a FROM products WHERE sku=?", (sku,)).fetchone()
        return r["a"] if r else 0

    def reserve(self, items):
        """All-or-nothing reservation. Returns list of SKUs lacking stock ([] = success).
        On shortage, anything reserved so far in this call is rolled back."""
        done, short = [], []
        for it in items:
            cur = self.conn.execute(
                "UPDATE products SET reserved = reserved + ? WHERE sku=? AND stock - reserved >= ?",
                (it["qty"], it["sku"], it["qty"]),
            )
            (done if cur.rowcount else short).append(it["sku"] if not cur.rowcount else it)
        if short:
            self.release(done)
        return short

    def release(self, items):
        for it in items:
            self.conn.execute(
                "UPDATE products SET reserved = reserved - ? WHERE sku=?", (it["qty"], it["sku"])
            )

    def commit(self, items):
        """Turn a reservation into a real stock deduction (when the parcel ships)."""
        for it in items:
            self.conn.execute(
                "UPDATE products SET stock = stock - ?, reserved = reserved - ? WHERE sku=?",
                (it["qty"], it["qty"], it["sku"]),
            )

    def low_stock(self, threshold=5):
        return [dict(r) for r in self.conn.execute(
            "SELECT sku,name,stock,reserved FROM products WHERE stock - reserved <= ? "
            "ORDER BY stock-reserved", (threshold,))]
