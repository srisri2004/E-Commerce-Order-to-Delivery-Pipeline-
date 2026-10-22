# E-Commerce Order-to-Delivery Pipeline

An event-driven order fulfilment system built as a **saga**: each order moves through a strict
state machine, and every failure triggers a compensating action (release stock, refund).
Pure Python 3.9+ standard library (SQLite) - no installs needed.

## Run
    python main.py                          # demo of all paths
    python -m unittest discover -s tests -t .   # 12 tests

## Order lifecycle
    CREATED -> INVENTORY_RESERVED -> PAID -> PACKED -> SHIPPED -> OUT_FOR_DELIVERY -> DELIVERED
       |              |                |        |
       |              +-> PAYMENT_FAILED (stock released)
       +-> OUT_OF_STOCK (partial reservations rolled back)
    CREATED / RESERVED / PAID / PACKED -> CANCELLED (stock released + payment refunded)

## Architecture
| Module | Responsibility |
|---|---|
| `ecom/models.py` | Statuses, legal transition table, exceptions |
| `ecom/db.py` | SQLite schema (products, orders, items, payments, shipments, events) |
| `ecom/events.py` | Event bus: persists every event (audit log) then dispatches to subscribers |
| `ecom/services/inventory.py` | Reserve / release / commit stock, all-or-nothing, never oversells |
| `ecom/services/payment.py` | Gateway abstraction (`FakeGateway`; swap for Stripe/Razorpay) |
| `ecom/services/shipping.py` | Carrier assignment, tracking numbers, shipment status |
| `ecom/services/notification.py` | Email notifications driven by events |
| `ecom/orchestrator.py` | The saga: place -> reserve -> pay -> pack -> ship -> deliver, plus cancel |
| `ecom/reports.py` | Status breakdown, revenue, refunds, top products, fulfilment time |

## Design decisions
- **Transactions per saga step** - each step commits atomically with its event.
- **Reserve vs. commit** - stock is *reserved* at order time and only *deducted* when shipped.
- **Idempotency keys** - retried `place_order` calls never create duplicate orders.
- **Money in integer cents** - no floating-point errors.
- **State machine guard** - illegal jumps (e.g. CREATED -> DELIVERED) raise `InvalidTransition`.
- **DB constraints** (`stock >= 0`, `reserved <= stock`) are a last line of defence against overselling.

## Extend it
- Replace `FakeGateway` with a real PSP and use `tok_fail*` style fakes only in tests.
- Swap the in-process `EventBus` for Kafka/RabbitMQ/SQS; handlers already take `(type, order_id, payload)`.
- Add a FastAPI layer: `POST /orders`, `POST /orders/{id}/cancel`, `POST /webhooks/carrier`.
- Use Postgres with `SELECT ... FOR UPDATE` for stock rows under real concurrency.
- Add returns (DELIVERED -> RETURN_REQUESTED -> REFUNDED) and partial shipments.
