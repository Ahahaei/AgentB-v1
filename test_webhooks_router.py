from fastapi.testclient import TestClient

from main import app

# --- domain event payloads ---

ORDER_CREATED = {
    "seller_id": "S001",
    "event_type": "order_created",
    "payload": {"order_id": "ORD-001", "sku": "WIDGET-42", "quantity": 2, "total_amount": 59.99},
}

ORDER_PAID = {
    "seller_id": "S001",
    "event_type": "order_paid",
    "payload": {"order_id": "ORD-001", "amount_paid": 59.99, "payment_method": "card"},
}

ORDER_SHIPPED = {
    "seller_id": "S001",
    "event_type": "order_shipped",
    "payload": {"order_id": "ORD-001", "tracking_number": "TRK-999", "carrier": "UPS"},
}

ORDER_CANCELED = {
    "seller_id": "S001",
    "event_type": "order_canceled",
    "payload": {"order_id": "ORD-002", "cancellation_reason": "buyer_requested"},
}


# --- domain events are recorded with no decision result ---

def test_order_created_is_recorded():
    with TestClient(app) as client:
        post_resp = client.post("/webhooks/sp-api", json=ORDER_CREATED)
        assert post_resp.status_code == 202
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"] is None


def test_order_paid_is_recorded():
    with TestClient(app) as client:
        post_resp = client.post("/webhooks/sp-api", json=ORDER_PAID)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"] is None


def test_order_shipped_is_recorded():
    with TestClient(app) as client:
        post_resp = client.post("/webhooks/sp-api", json=ORDER_SHIPPED)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"] is None


def test_order_canceled_is_recorded():
    with TestClient(app) as client:
        post_resp = client.post("/webhooks/sp-api", json=ORDER_CANCELED)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "completed"
    assert data["result"] is None


# --- layer boundary enforcement ---

def test_webhooks_rejects_monitoring_event():
    monitoring_event = {
        "seller_id": "S001",
        "event_type": "inventory_low",
        "payload": {"sku": "X", "current_quantity": 1},
    }
    with TestClient(app) as client:
        resp = client.post("/webhooks/sp-api", json=monitoring_event)
    assert resp.status_code == 422


def test_events_rejects_domain_event():
    with TestClient(app) as client:
        resp = client.post("/events", json=ORDER_CREATED)
    assert resp.status_code == 422


def test_domain_event_inactive_seller_fails():
    event = {**ORDER_CREATED, "seller_id": "S003"}
    with TestClient(app) as client:
        post_resp = client.post("/webhooks/sp-api", json=event)
        event_id = post_resp.json()["event_id"]
        get_resp = client.get(f"/events/{event_id}")

    data = get_resp.json()
    assert data["status"] == "failed"
    assert "not active" in data["error"]
