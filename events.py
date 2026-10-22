"""Tiny in-process event bus. Every event is persisted (audit log) then dispatched."""
import json
from collections import defaultdict


class EventBus:
    def __init__(self, conn):
        self.conn = conn
        self._handlers = defaultdict(list)

    def subscribe(self, event_type, handler):
        self._handlers[event_type].append(handler)

    def publish(self, event_type, order_id=None, **payload):
        self.conn.execute(
            "INSERT INTO events(order_id, type, payload) VALUES (?,?,?)",
            (order_id, event_type, json.dumps(payload)),
        )
        for h in self._handlers[event_type] + self._handlers["*"]:
            h(event_type, order_id, payload)

    def timeline(self, order_id):
        rows = self.conn.execute(
            "SELECT ts, type, payload FROM events WHERE order_id=? ORDER BY id", (order_id,)
        ).fetchall()
        return [(r["ts"], r["type"], json.loads(r["payload"] or "{}")) for r in rows]
