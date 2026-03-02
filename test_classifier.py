from app.engine.classifier import classify
from app.models.event import EventType
from app.models.intent import Intent


def test_inventory_low_maps_to_reorder():
    assert classify(EventType.INVENTORY_LOW) == Intent.REORDER


def test_order_spike_detected_maps_to_flag_order_spike():
    assert classify(EventType.ORDER_SPIKE_DETECTED) == Intent.FLAG_ORDER_SPIKE
