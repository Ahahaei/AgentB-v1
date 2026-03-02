from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from app.models.decision import DecisionResult


class EventType(str, Enum):
    INVENTORY_LOW = "inventory_low"
    ORDER_SPIKE_DETECTED = "order_spike_detected"


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
