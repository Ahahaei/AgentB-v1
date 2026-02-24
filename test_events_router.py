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
