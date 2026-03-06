import hashlib
import hmac
import json
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from main import app

# Known signing secret used to generate valid signatures in tests
TEST_SIGNING_SECRET = "test-signing-secret-abc123"

# S002 inventory_low → HIGH risk → creates PendingApproval
INVENTORY_HIGH = {
    "seller_id": "S002",
    "event_type": "inventory_low",
    "payload": {"sku": "BULK-01", "current_quantity": 10},
}


@pytest.fixture(autouse=True)
def set_signing_secret(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", TEST_SIGNING_SECRET)


def _make_body(approval_id: str, action_id: str, user_id: str = "U_TESTUSER") -> bytes:
    payload = {
        "type": "block_actions",
        "user": {"id": user_id, "name": "testuser"},
        "actions": [{"action_id": action_id, "value": approval_id}],
    }
    return f"payload={urllib.parse.quote(json.dumps(payload))}".encode()


def _sign(body: bytes, secret: str, timestamp: str) -> str:
    sig_base = f"v0:{timestamp}:{body.decode()}"
    mac = hmac.new(secret.encode(), sig_base.encode(), hashlib.sha256)
    return "v0=" + mac.hexdigest()


def _post_interaction(client: TestClient, body: bytes, secret: str = TEST_SIGNING_SECRET):
    timestamp = str(int(time.time()))
    return client.post(
        "/slack/interactions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": _sign(body, secret, timestamp),
        },
    )


def _get_approval_id(client: TestClient) -> str:
    post_resp = client.post("/events", json=INVENTORY_HIGH)
    event_id = post_resp.json()["event_id"]
    event_data = client.get(f"/events/{event_id}").json()
    return event_data["result"]["execution_result"]["approval_id"]


# --- approve via Slack ---

def test_approve_via_slack_returns_ok():
    with TestClient(app) as client:
        approval_id = _get_approval_id(client)
        body = _make_body(approval_id, "approve_action", "U_ALICE")
        resp = _post_interaction(client, body)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_approve_via_slack_sets_status():
    with TestClient(app) as client:
        approval_id = _get_approval_id(client)
        _post_interaction(client, _make_body(approval_id, "approve_action", "U_ALICE"))
        approval = client.get(f"/approvals/{approval_id}").json()
    assert approval["status"] == "approved"
    assert approval["resolved_by"] == "U_ALICE"
    assert approval["resolved_at"] is not None


# --- reject via Slack ---

def test_reject_via_slack_sets_status():
    with TestClient(app) as client:
        approval_id = _get_approval_id(client)
        _post_interaction(client, _make_body(approval_id, "reject_action", "U_BOB"))
        approval = client.get(f"/approvals/{approval_id}").json()
    assert approval["status"] == "rejected"
    assert approval["resolved_by"] == "U_BOB"


# --- signature verification ---

def test_invalid_signature_is_rejected():
    with TestClient(app) as client:
        approval_id = _get_approval_id(client)
        body = _make_body(approval_id, "approve_action")
        resp = _post_interaction(client, body, secret="wrong-secret")
    assert resp.status_code == 401


def test_missing_signature_is_rejected():
    with TestClient(app) as client:
        approval_id = _get_approval_id(client)
        body = _make_body(approval_id, "approve_action")
        resp = client.post(
            "/slack/interactions",
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    assert resp.status_code == 401


# --- conflict / idempotency ---

def test_double_approve_via_slack_is_conflict():
    with TestClient(app) as client:
        approval_id = _get_approval_id(client)
        body = _make_body(approval_id, "approve_action")
        _post_interaction(client, body)
        resp = _post_interaction(client, body)
    assert resp.status_code == 409


def test_approve_after_reject_via_slack_is_conflict():
    with TestClient(app) as client:
        approval_id = _get_approval_id(client)
        _post_interaction(client, _make_body(approval_id, "reject_action"))
        resp = _post_interaction(client, _make_body(approval_id, "approve_action"))
    assert resp.status_code == 409


# --- unknown action ---

def test_unknown_action_is_bad_request():
    with TestClient(app) as client:
        approval_id = _get_approval_id(client)
        body = _make_body(approval_id, "unknown_action")
        resp = _post_interaction(client, body)
    assert resp.status_code == 400


# --- not found ---

def test_approval_not_found():
    with TestClient(app) as client:
        body = _make_body("nonexistent-id", "approve_action")
        resp = _post_interaction(client, body)
    assert resp.status_code == 404
