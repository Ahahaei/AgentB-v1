from fastapi.testclient import TestClient

from main import app

# S002 inventory_low → HIGH risk (200 units * $5 = $1000 > $800 limit)
INVENTORY_HIGH = {
    "seller_id": "S002",
    "event_type": "inventory_low",
    "payload": {"sku": "BULK-01", "current_quantity": 10},
}


def _post_and_get_event(client: TestClient, payload: dict) -> dict:
    post_resp = client.post("/events", json=payload)
    assert post_resp.status_code == 202
    event_id = post_resp.json()["event_id"]
    get_resp = client.get(f"/events/{event_id}")
    return get_resp.json()


# --- approval is created on ESCALATED ---

def test_high_risk_event_produces_approval_id():
    with TestClient(app) as client:
        data = _post_and_get_event(client, INVENTORY_HIGH)
    assert data["result"]["execution_result"]["status"] == "escalated"
    assert data["result"]["execution_result"]["approval_id"] is not None


def test_low_risk_event_has_no_approval_id():
    low_risk = {
        "seller_id": "S001",
        "event_type": "inventory_low",
        "payload": {"sku": "WIDGET-42", "current_quantity": 5},
    }
    with TestClient(app) as client:
        data = _post_and_get_event(client, low_risk)
    assert data["result"]["execution_result"]["status"] == "executed"
    assert data["result"]["execution_result"]["approval_id"] is None


# --- GET /approvals/{id} ---

def test_get_pending_approval():
    with TestClient(app) as client:
        event_data = _post_and_get_event(client, INVENTORY_HIGH)
        approval_id = event_data["result"]["execution_result"]["approval_id"]
        resp = client.get(f"/approvals/{approval_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["resolved_at"] is None
    assert data["resolved_by"] is None


def test_get_approval_links_back_to_event():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=INVENTORY_HIGH)
        event_id = post_resp.json()["event_id"]
        event_data = client.get(f"/events/{event_id}").json()
        approval_id = event_data["result"]["execution_result"]["approval_id"]
        approval_data = client.get(f"/approvals/{approval_id}").json()

    assert approval_data["event_id"] == event_id
    assert approval_data["seller_id"] == "S002"
    assert approval_data["intent"] == "reorder"


def test_get_approval_not_found():
    with TestClient(app) as client:
        resp = client.get("/approvals/nonexistent-id")
    assert resp.status_code == 404


# --- POST /approvals/{id}/approve ---

def test_approve_sets_status_and_resolved_at():
    with TestClient(app) as client:
        event_data = _post_and_get_event(client, INVENTORY_HIGH)
        approval_id = event_data["result"]["execution_result"]["approval_id"]
        resp = client.post(f"/approvals/{approval_id}/approve")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["resolved_at"] is not None
    assert data["resolved_by"] == "api"


def test_approve_not_found():
    with TestClient(app) as client:
        resp = client.post("/approvals/nonexistent-id/approve")
    assert resp.status_code == 404


# --- POST /approvals/{id}/reject ---

def test_reject_sets_status_and_resolved_at():
    with TestClient(app) as client:
        event_data = _post_and_get_event(client, INVENTORY_HIGH)
        approval_id = event_data["result"]["execution_result"]["approval_id"]
        resp = client.post(f"/approvals/{approval_id}/reject")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["resolved_at"] is not None
    assert data["resolved_by"] == "api"


def test_reject_not_found():
    with TestClient(app) as client:
        resp = client.post("/approvals/nonexistent-id/reject")
    assert resp.status_code == 404


# --- idempotency / conflict ---

def test_double_approve_is_conflict():
    with TestClient(app) as client:
        event_data = _post_and_get_event(client, INVENTORY_HIGH)
        approval_id = event_data["result"]["execution_result"]["approval_id"]
        client.post(f"/approvals/{approval_id}/approve")
        resp = client.post(f"/approvals/{approval_id}/approve")
    assert resp.status_code == 409


def test_approve_after_reject_is_conflict():
    with TestClient(app) as client:
        event_data = _post_and_get_event(client, INVENTORY_HIGH)
        approval_id = event_data["result"]["execution_result"]["approval_id"]
        client.post(f"/approvals/{approval_id}/reject")
        resp = client.post(f"/approvals/{approval_id}/approve")
    assert resp.status_code == 409


# --- post-approval SP API execution ---

def test_approve_executes_sp_api():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=INVENTORY_HIGH)
        event_id = post_resp.json()["event_id"]
        event_data = client.get(f"/events/{event_id}").json()
        approval_id = event_data["result"]["execution_result"]["approval_id"]
        client.post(f"/approvals/{approval_id}/approve")
        updated = client.get(f"/events/{event_id}").json()
    sp = updated["result"]["execution_result"]["sp_api_result"]
    assert sp is not None
    assert sp["status"] == "success"
    assert sp["sku"] == "BULK-01"
    assert sp["order_id"].startswith("MOCK-PO-")


def test_reject_does_not_execute_sp_api():
    with TestClient(app) as client:
        post_resp = client.post("/events", json=INVENTORY_HIGH)
        event_id = post_resp.json()["event_id"]
        event_data = client.get(f"/events/{event_id}").json()
        approval_id = event_data["result"]["execution_result"]["approval_id"]
        client.post(f"/approvals/{approval_id}/reject")
        updated = client.get(f"/events/{event_id}").json()
    assert updated["result"]["execution_result"]["sp_api_result"] is None
