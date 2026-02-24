from app.engine.classifier import classify
from app.models.event import EventType
from app.models.intent import Intent


def test_inventory_low_maps_to_reorder():
    assert classify(EventType.INVENTORY_LOW) == Intent.REORDER
