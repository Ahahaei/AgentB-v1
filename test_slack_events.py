"""
Phase 2 — POST /slack/events endpoint tests.

Covers: URL verification challenge, HMAC rejection, bot filtering,
seller lookup, deduplication, and BackgroundTask dispatch.
"""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app

TEST_SIGNING_SECRET = "test-signing-secret-abc123"


@pytest.fixture(autouse=True)
def set_signing_secret(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", TEST_SIGNING_SECRET)


@pytest.fixture(autouse=True)
def clear_seen_event_ids():
    """Reset the in-process dedup set between tests."""
    import app.routers.slack as slack_router
    slack_router._seen_event_ids.clear()
    yield
    slack_router._seen_event_ids.clear()


def _sign(body: bytes, secret: str, timestamp: str) -> str:
    sig_base = f"v0:{timestamp}:{body.decode()}"
    mac = hmac.new(secret.encode(), sig_base.encode(), hashlib.sha256)
    return "v0=" + mac.hexdigest()


def _post_event(client: TestClient, data: dict, secret: str = TEST_SIGNING_SECRET):
    body = json.dumps(data).encode()
    timestamp = str(int(time.time()))
    return client.post(
        "/slack/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": _sign(body, secret, timestamp),
        },
    )


def _message_event(user_id: str, text: str, event_id: str = "Ev001") -> dict:
    return {
        "type": "event_callback",
        "event_id": event_id,
        "event": {
            "type": "message",
            "user": user_id,
            "text": text,
            "channel": "D_CHANNEL",
        },
    }


# --- URL verification challenge ---

def test_url_verification_returns_challenge():
    with TestClient(app) as client:
        resp = _post_event(client, {
            "type": "url_verification",
            "challenge": "abc123xyz",
        })
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "abc123xyz"


# --- HMAC signature verification ---

def test_invalid_signature_is_rejected():
    with TestClient(app) as client:
        resp = _post_event(client, _message_event("U_MOCK_S001", "hello"), secret="wrong-secret")
    assert resp.status_code == 401


def test_missing_signature_is_rejected():
    with TestClient(app) as client:
        body = json.dumps(_message_event("U_MOCK_S001", "hello")).encode()
        resp = client.post(
            "/slack/events",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 401


# --- Bot message filtering ---

def test_bot_message_is_ignored():
    with TestClient(app) as client:
        data = {
            "type": "event_callback",
            "event_id": "Ev_bot",
            "event": {
                "type": "message",
                "bot_id": "B12345",
                "text": "I am the bot",
                "channel": "D_CHANNEL",
            },
        }
        resp = _post_event(client, data)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_bot_subtype_message_is_ignored():
    with TestClient(app) as client:
        data = {
            "type": "event_callback",
            "event_id": "Ev_sub",
            "event": {
                "type": "message",
                "subtype": "bot_message",
                "text": "automated message",
                "channel": "D_CHANNEL",
            },
        }
        resp = _post_event(client, data)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# --- Unknown event types ---

def test_non_event_callback_type_is_ok():
    with TestClient(app) as client:
        resp = _post_event(client, {"type": "something_else"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_non_message_event_is_ignored():
    with TestClient(app) as client:
        data = {
            "type": "event_callback",
            "event_id": "Ev_reaction",
            "event": {"type": "reaction_added", "user": "U_MOCK_S001"},
        }
        resp = _post_event(client, data)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# --- Seller lookup ---

def test_unknown_slack_user_is_silently_dropped():
    with TestClient(app) as client:
        resp = _post_event(client, _message_event("U_NOBODY", "hello"))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_known_seller_message_returns_ok():
    with TestClient(app) as client:
        resp = _post_event(client, _message_event("U_MOCK_S001", "reorder 50 units of WIDGET-42"))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# --- BackgroundTask dispatch ---

def test_known_seller_dispatches_handle_message():
    with TestClient(app) as client:
        with patch("app.routers.slack.handle_message") as mock_handler:
            _post_event(client, _message_event("U_MOCK_S001", "show my approvals", event_id="Ev_dispatch"))

    mock_handler.assert_called_once()
    seller_arg, text_arg, channel_arg = mock_handler.call_args.args
    assert seller_arg.id == "S001"
    assert text_arg == "show my approvals"
    assert channel_arg == "D_CHANNEL"


def test_unknown_seller_does_not_dispatch_handle_message():
    with TestClient(app) as client:
        with patch("app.routers.slack.handle_message") as mock_handler:
            _post_event(client, _message_event("U_NOBODY", "hello", event_id="Ev_nodispatch"))

    mock_handler.assert_not_called()


# --- Deduplication ---

def test_duplicate_event_id_is_processed_once():
    event = _message_event("U_MOCK_S001", "reorder 10 units of SKU-99", event_id="Ev_dup")
    with TestClient(app) as client:
        with patch("app.routers.slack.handle_message") as mock_handler:
            _post_event(client, event)
            _post_event(client, event)  # same event_id

    assert mock_handler.call_count == 1
