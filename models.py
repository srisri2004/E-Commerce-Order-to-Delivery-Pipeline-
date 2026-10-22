from enum import Enum


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    INVENTORY_RESERVED = "INVENTORY_RESERVED"
    PAID = "PAID"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    # terminal / failure states
    OUT_OF_STOCK = "OUT_OF_STOCK"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    CANCELLED = "CANCELLED"


S = OrderStatus
# Legal state machine transitions: current -> allowed next states
TRANSITIONS = {
    S.CREATED: {S.INVENTORY_RESERVED, S.OUT_OF_STOCK, S.CANCELLED},
    S.INVENTORY_RESERVED: {S.PAID, S.PAYMENT_FAILED, S.CANCELLED},
    S.PAID: {S.PACKED, S.CANCELLED},
    S.PACKED: {S.SHIPPED, S.CANCELLED},
    S.SHIPPED: {S.OUT_FOR_DELIVERY},
    S.OUT_FOR_DELIVERY: {S.DELIVERED},
    S.DELIVERED: set(),
    S.OUT_OF_STOCK: set(),
    S.PAYMENT_FAILED: set(),
    S.CANCELLED: set(),
}
TERMINAL = {s for s, nxt in TRANSITIONS.items() if not nxt}
CANCELLABLE = {S.CREATED, S.INVENTORY_RESERVED, S.PAID, S.PACKED}


class PipelineError(Exception):
    pass


class InvalidTransition(PipelineError):
    pass


class ValidationError(PipelineError):
    pass
