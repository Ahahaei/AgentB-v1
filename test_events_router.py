from fastapi.testclient import TestClient

from main import app

VALID_EVENT = {
    "seller_id": "S001",
    "event_type": "inventory_low",
    "payload": {"sku": "ABC-123", "current_quantity": 3},
}


def test_post_event_returns_202():
    with TestClient(app) as client:
        resp = client.post("/events", json=VALID_EVENT)
    assert resp.status_code == 202
    data = resp.json()
    assert "event_id" in data
    assert data["status"] == "pending"


def test_get_event_completes_with_decision():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=VALID_EVENT)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"]["intent"] == "reorder"
    assert data["result"]["policy_result"]["risk_level"] == "LOW"
    assert data["result"]["execution_result"]["status"] == "executed"


def test_high_risk_seller_escalates():
    event = {**VALID_EVENT, "seller_id": "S002"}
    with TestClient(app) as client:
        post_resp = client.post("/events", json=event)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"]["policy_result"]["risk_level"] == "HIGH"
    assert data["result"]["execution_result"]["status"] == "escalated"


def test_inactive_seller_fails_pipeline():
    event = {**VALID_EVENT, "seller_id": "S003"}
    with TestClient(app) as client:
        post_resp = client.post("/events", json=event)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "failed"
    assert "not active" in data["error"]


def test_unknown_seller_fails_pipeline():
    event = {**VALID_EVENT, "seller_id": "UNKNOWN"}
    with TestClient(app) as client:
        post_resp = client.post("/events", json=event)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "failed"
    assert "not found" in data["error"]


def test_get_nonexistent_event_returns_404():
    with TestClient(app) as client:
        resp = client.get("/events/does-not-exist")
    assert resp.status_code == 404


# --- order_spike_detected ---

SPIKE_EVENT_LOW = {
    "seller_id": "S001",
    "event_type": "order_spike_detected",
    # 20/12 = 1.67x — below S001 threshold (2.0) → LOW
    "payload": {"order_count": 20, "baseline_count": 12, "window_minutes": 60},
}

SPIKE_EVENT_HIGH = {
    "seller_id": "S001",
    "event_type": "order_spike_detected",
    # 30/12 = 2.5x — above S001 threshold (2.0) → HIGH
    "payload": {"order_count": 30, "baseline_count": 12, "window_minutes": 60},
}


def test_order_spike_low_risk_is_auto_executed():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=SPIKE_EVENT_LOW)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"]["intent"] == "flag_order_spike"
    assert data["result"]["policy_result"]["risk_level"] == "LOW"
    assert data["result"]["execution_result"]["status"] == "executed"


def test_order_spike_high_risk_is_escalated():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=SPIKE_EVENT_HIGH)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"]["intent"] == "flag_order_spike"
    assert data["result"]["policy_result"]["risk_level"] == "HIGH"
    assert data["result"]["execution_result"]["status"] == "escalated"


def test_order_spike_result_has_no_quantity_or_spend():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=SPIKE_EVENT_LOW)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    policy = get_resp.json()["result"]["policy_result"]
    assert policy["recommended_quantity"] is None
    assert policy["estimated_spend"] is None


# --- high_refund_rate_detected ---

REFUND_EVENT_LOW = {
    "seller_id": "S001",
    "event_type": "high_refund_rate_detected",
    # 5/100 = 5% — below S001 threshold (10%) → LOW
    "payload": {"refund_count": 5, "order_count": 100, "window_minutes": 1440},
}

REFUND_EVENT_HIGH = {
    "seller_id": "S001",
    "event_type": "high_refund_rate_detected",
    # 15/100 = 15% — above S001 threshold (10%) → HIGH
    "payload": {"refund_count": 15, "order_count": 100, "window_minutes": 1440},
}


def test_refund_rate_low_risk_is_auto_executed():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=REFUND_EVENT_LOW)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"]["intent"] == "flag_refund_rate"
    assert data["result"]["policy_result"]["risk_level"] == "LOW"
    assert data["result"]["execution_result"]["status"] == "executed"


def test_refund_rate_high_risk_is_escalated():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=REFUND_EVENT_HIGH)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"]["intent"] == "flag_refund_rate"
    assert data["result"]["policy_result"]["risk_level"] == "HIGH"
    assert data["result"]["execution_result"]["status"] == "escalated"
