import itertools


class FakeGateway:
    """Deterministic stand-in for Stripe/Razorpay. Tokens starting with 'tok_fail' are declined."""
    _ids = itertools.count(1000)

    def charge(self, token, amount_cents):
        if token.startswith("tok_fail"):
            return False, None, "card_declined"
        return True, f"txn_{next(self._ids)}", None

    def refund(self, txn_ref):
        return True, f"re_{txn_ref}"


class PaymentService:
    def __init__(self, conn, gateway=None):
        self.conn = conn
        self.gateway = gateway or FakeGateway()

    def charge(self, order_id, token, amount_cents):
        ok, ref, err = self.gateway.charge(token, amount_cents)
        self.conn.execute(
            "INSERT INTO payments(order_id,amount_cents,status,txn_ref) VALUES (?,?,?,?)",
            (order_id, amount_cents, "SUCCEEDED" if ok else "FAILED", ref),
        )
        return ok, ref, err

    def refund(self, order_id):
        row = self.conn.execute(
            "SELECT id,txn_ref FROM payments WHERE order_id=? AND status='SUCCEEDED'", (order_id,)
        ).fetchone()
        if not row:
            return False
        self.gateway.refund(row["txn_ref"])
        self.conn.execute("UPDATE payments SET status='REFUNDED' WHERE id=?", (row["id"],))
        return True
