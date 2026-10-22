import itertools

CARRIERS = ["BlueDart", "Delhivery", "DTDC"]


class ShippingService:
    _seq = itertools.count(1)

    def __init__(self, conn):
        self.conn = conn

    def create_shipment(self, order_id):
        n = next(self._seq)
        carrier = CARRIERS[order_id % len(CARRIERS)]
        tracking = f"{carrier[:2].upper()}{order_id:06d}{n:04d}"
        self.conn.execute(
            "INSERT INTO shipments(order_id,carrier,tracking,status) VALUES (?,?,?,'LABEL_CREATED')",
            (order_id, carrier, tracking),
        )
        return carrier, tracking

    def update(self, order_id, status):
        self.conn.execute("UPDATE shipments SET status=? WHERE order_id=?", (status, order_id))

    def get(self, order_id):
        r = self.conn.execute("SELECT * FROM shipments WHERE order_id=?", (order_id,)).fetchone()
        return dict(r) if r else None
