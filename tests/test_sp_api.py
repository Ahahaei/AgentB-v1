from fastapi.testclient import TestClient

from main import app

# S001 inventory_low → LOW risk (40 units * $8 = $320 < $500 limit)
REORDER_LOW = {
    "seller_id": "S001",
    "event_type": "inventory_low",
    "payload": {"sku": "WIDGET-42", "current_quantity": 3},
}

# S001 order_spike → LOW risk (15/10 = 1.5x < 2.0x threshold)
SPIKE_LOW = {
    "seller_id": "S001",
    "event_type": "order_spike_detected",
    "payload": {"sku": "WIDGET-42", "baseline_orders": 10, "current_orders": 15},
}

# S001 high_refund_rate → LOW risk (8% < 10% threshold)
REFUND_LOW = {
    "seller_id": "S001",
    "event_type": "high_refund_rate_detected",
    "payload": {"refund_rate": 0.08, "total_orders": 100},
}

# S002 inventory_low → HIGH risk (200 units * $5 = $1000 > $800 limit)
REORDER_HIGH = {
    "seller_id": "S002",
    "event_type": "inventory_low",
    "payload": {"sku": "BULK-01", "current_quantity": 5},
}


def _get_result(client, payload):
    post = client.post("/events", json=payload)
    event_id = post.json()["event_id"]
    return client.get(f"/events/{event_id}").json()


# --- EXECUTED path produces sp_api_result ---

def test_reorder_low_risk_has_sp_api_result():
    with TestClient(app) as client:
        data = _get_result(client, REORDER_LOW)
    er = data["result"]["execution_result"]
    assert er["status"] == "executed"
    assert er["sp_api_result"] is not None
    assert er["sp_api_result"]["status"] == "success"
    assert er["sp_api_result"]["sku"] == "WIDGET-42"
    assert er["sp_api_result"]["quantity"] == 40  # reorder_quantity from seller policy
    assert "order_id" in er["sp_api_result"]


def test_reorder_mock_order_id_format():
    with TestClient(app) as client:
        data = _get_result(client, REORDER_LOW)
    order_id = data["result"]["execution_result"]["sp_api_result"]["order_id"]
    assert order_id.startswith("MOCK-PO-")


def test_order_spike_low_risk_is_acknowledged():
    with TestClient(app) as client:
        data = _get_result(client, SPIKE_LOW)
    er = data["result"]["execution_result"]
    assert er["status"] == "executed"
    assert er["sp_api_result"]["status"] == "acknowledged"
    assert er["sp_api_result"]["intent"] == "flag_order_spike"


def test_refund_rate_low_risk_is_acknowledged():
    with TestClient(app) as client:
        data = _get_result(client, REFUND_LOW)
    er = data["result"]["execution_result"]
    assert er["status"] == "executed"
    assert er["sp_api_result"]["status"] == "acknowledged"
    assert er["sp_api_result"]["intent"] == "flag_refund_rate"


# --- ESCALATED path has no sp_api_result ---

def test_high_risk_escalated_has_no_sp_api_result():
    with TestClient(app) as client:
        data = _get_result(client, REORDER_HIGH)
    er = data["result"]["execution_result"]
    assert er["status"] == "escalated"
    assert er["sp_api_result"] is None
    assert er["approval_id"] is not None


# --- sp_api_result is persisted in DB ---

def test_sp_api_result_persisted():
    with TestClient(app) as client:
        post = client.post("/events", json=REORDER_LOW)
        event_id = post.json()["event_id"]
        data = client.get(f"/events/{event_id}").json()
    assert data["result"]["execution_result"]["sp_api_result"]["status"] == "success"
