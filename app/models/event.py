from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from app.models.decision import DecisionResult


class EventLayer(str, Enum):
    DOMAIN = "domain"          # Layer 1 — raw facts from SP API, record only
    MONITORING = "monitoring"  # Layer 2 — derived signals, run decision pipeline


class EventType(str, Enum):
    # Layer 1 — Domain
    ORDER_CREATED = "order_created"
    ORDER_PAID = "order_paid"
    ORDER_SHIPPED = "order_shipped"
    ORDER_CANCELED = "order_canceled"
    # Layer 2 — Monitoring
    INVENTORY_LOW = "inventory_low"
    ORDER_SPIKE_DETECTED = "order_spike_detected"
    HIGH_REFUND_RATE_DETECTED = "high_refund_rate_detected"


EVENT_LAYER_MAP: dict[str, EventLayer] = {
    EventType.ORDER_CREATED: EventLayer.DOMAIN,
    EventType.ORDER_PAID: EventLayer.DOMAIN,
    EventType.ORDER_SHIPPED: EventLayer.DOMAIN,
    EventType.ORDER_CANCELED: EventLayer.DOMAIN,
    EventType.INVENTORY_LOW: EventLayer.MONITORING,
    EventType.ORDER_SPIKE_DETECTED: EventLayer.MONITORING,
    EventType.HIGH_REFUND_RATE_DETECTED: EventLayer.MONITORING,
}

DOMAIN_EVENT_TYPES = {t for t, l in EVENT_LAYER_MAP.items() if l == EventLayer.DOMAIN}
MONITORING_EVENT_TYPES = {t for t, l in EVENT_LAYER_MAP.items() if l == EventLayer.MONITORING}


class EventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EventInput(BaseModel):
    seller_id: str
    event_type: EventType
    payload: dict[str, Any]


class EventRecord(BaseModel):
    id: str
    seller_id: str
    event_type: EventType
    payload: dict[str, Any]
    status: EventStatus
    result: Optional[DecisionResult] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
