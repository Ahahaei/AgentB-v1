from app.models.event import EventType
from app.models.intent import Intent


def classify(event_type: EventType) -> Intent:
    if event_type == EventType.INVENTORY_LOW:
        return Intent.REORDER
    if event_type == EventType.ORDER_SPIKE_DETECTED:
        return Intent.FLAG_ORDER_SPIKE
    return Intent.UNKNOWN
