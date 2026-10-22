MESSAGES = {
    "OrderCreated": "We received your order #{id}.",
    "PaymentSucceeded": "Payment received for order #{id}.",
    "OrderOutOfStock": "Sorry, an item in order #{id} is out of stock.",
    "PaymentFailed": "Payment failed for order #{id}. Please try another card.",
    "OrderShipped": "Order #{id} shipped via {carrier}. Tracking: {tracking}.",
    "OrderOutForDelivery": "Order #{id} is out for delivery today.",
    "OrderDelivered": "Order #{id} was delivered. Enjoy!",
    "OrderCancelled": "Order #{id} was cancelled. Any payment will be refunded.",
}


class NotificationService:
    """Subscribes to all events and 'sends' emails (kept in an in-memory outbox)."""

    def __init__(self, conn):
        self.conn = conn
        self.outbox = []

    def handle(self, event_type, order_id, payload):
        tpl = MESSAGES.get(event_type)
        if not tpl or order_id is None:
            return
        row = self.conn.execute("SELECT email FROM orders WHERE id=?", (order_id,)).fetchone()
        self.outbox.append((row["email"], tpl.format(id=order_id, **payload)))
