"""Demo: runs orders through every path of the pipeline."""
from ecom.orchestrator import OrderPipeline
from ecom.reports import Reports


def money(c):
    return f"Rs {c / 100:,.2f}"


def main():
    p = OrderPipeline()
    for sku, name, price, stock in [
        ("LAP-01", "Laptop", 55_000_00, 5), ("MOU-01", "Wireless Mouse", 799_00, 50),
        ("KEY-01", "Keyboard", 2_499_00, 10), ("HDP-01", "Headphones", 3_999_00, 2),
    ]:
        p.inventory.add_product(sku, name, price, stock)

    orders = [
        ("happy path",    "Asha",   "asha@example.com",   [("LAP-01", 1), ("MOU-01", 2)], "tok_ok"),
        ("happy path 2",  "Ravi",   "ravi@example.com",   [("KEY-01", 1)], "tok_ok"),
        ("out of stock",  "Meena",  "meena@example.com",  [("HDP-01", 3), ("MOU-01", 1)], "tok_ok"),
        ("card declined", "Kiran",  "kiran@example.com",  [("KEY-01", 2)], "tok_fail_1"),
        ("cancel + refund", "Sana", "sana@example.com",   [("HDP-01", 1)], "tok_ok"),
    ]
    ids = {}
    print("=== Processing orders ===")
    for label, cust, mail, items, tok in orders:
        oid = p.place_order(cust, mail, [{"sku": s, "qty": q} for s, q in items], tok,
                            idempotency_key=f"demo-{label}")
        ids[label] = oid
        if label == "cancel + refund":
            p.process(oid, auto_ship=False)     # paid, not yet shipped
            p.cancel(oid)
            status = "CANCELLED"
        else:
            status = p.run_to_delivery(oid).value
        print(f"  #{oid:<2} {label:<16} -> {status}")

    r = Reports(p.conn)
    print("\n=== Report ===")
    print("Orders by status :", r.status_breakdown())
    print("Net revenue      :", money(r.revenue_cents()), "| refunded:", money(r.refunded_cents()))
    print("Top products     :", r.top_products())
    print("Low stock        :", [(x['sku'], x['stock'] - x['reserved']) for x in p.inventory.low_stock(3)])

    oid = ids["happy path"]
    print(f"\n=== Event timeline for order #{oid} ===")
    for ts, typ, payload in p.bus.timeline(oid):
        print(f"  {ts}  {typ:<20} {payload}")

    print("\n=== Customer emails (first 8) ===")
    for to, body in p.notifier.outbox[:8]:
        print(f"  {to:<18} {body}")


if __name__ == "__main__":
    main()
