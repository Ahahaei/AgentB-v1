"""
Phase 3 — LLM agent tests.

All tests mock the Anthropic client. No real API calls are made.
Tool handler tests use the in-memory SQLite DB from conftest.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.store as store
from app.llm import agent as agent_module
from app.llm import tool_handlers
from app.mock.sellers import MOCK_SELLERS
from main import app

# Seller S001 — LOW risk reorders (40 units * $8 = $320, within limits)
S001 = MOCK_SELLERS[0]
# Seller S002 — HIGH risk reorders (200 units * $5 = $1000, above limits)
S002 = MOCK_SELLERS[1]


# ---------------------------------------------------------------------------
# Helpers: build mock Anthropic responses
# ---------------------------------------------------------------------------

def _make_tool_use_response(tool_name: str, tool_input: dict, tool_id: str = "tu_001"):
    """Mock a response where Claude chose to call a tool."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = tool_id
    tool_block.name = tool_name
    tool_block.input = tool_input

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_block]
    return response


def _make_text_response(text: str):
    """Mock a response where Claude replied with plain text."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]
    return response


# ---------------------------------------------------------------------------
# agent.run_agent — tool dispatch
# ---------------------------------------------------------------------------

@patch("app.llm.agent._get_client")
def test_agent_dispatches_reorder_sku(mock_get_client):
    tool_response = _make_tool_use_response("reorder_sku", {"sku": "WIDGET-42", "quantity": 10})
    followup = _make_text_response("Done! Reorder placed for 10 units of WIDGET-42.")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [tool_response, followup]
    mock_get_client.return_value = mock_client

    # The handler only enqueues now, so there is no decision to fake.
    with patch("app.llm.tool_handlers.store.ingest_internal_event"):
        reply = agent_module.run_agent("reorder 10 units of WIDGET-42", S001)

    assert "done" in reply.lower() or "reorder" in reply.lower()
    assert mock_client.messages.create.call_count == 2


@patch("app.llm.agent._get_client")
def test_agent_passes_the_reply_channel_to_the_tool(mock_get_client):
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_tool_use_response("reorder_sku", {"sku": "WIDGET-42", "quantity": 10}),
        _make_text_response("Queued."),
    ]
    mock_get_client.return_value = mock_client

    with patch("app.llm.tool_handlers.reorder_sku") as mock_reorder:
        mock_reorder.return_value = "Queued."
        agent_module.run_agent("reorder 10 WIDGET-42", S001, reply_channel="C_DM_001")

    assert mock_reorder.call_args.kwargs["reply_channel"] == "C_DM_001"


@patch("app.llm.agent._get_client")
def test_agent_dispatches_list_approvals(mock_get_client):
    tool_response = _make_tool_use_response("list_approvals", {})
    followup = _make_text_response("You have no pending approvals.")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [tool_response, followup]
    mock_get_client.return_value = mock_client

    with patch("app.llm.tool_handlers.store.get_pending_approvals_for_seller", return_value=[]):
        reply = agent_module.run_agent("show my approvals", S001)

    assert "approvals" in reply.lower()
    assert mock_client.messages.create.call_count == 2


@patch("app.llm.agent._get_client")
def test_agent_dispatches_get_refund_rate(mock_get_client):
    tool_response = _make_tool_use_response("get_refund_rate", {})
    followup = _make_text_response("Your refund rate is 5.0%.")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [tool_response, followup]
    mock_get_client.return_value = mock_client

    with patch("app.llm.tool_handlers.store.get_recent_events_by_type", return_value=[]):
        reply = agent_module.run_agent("what is my refund rate?", S001)

    assert "refund" in reply.lower()
    assert mock_client.messages.create.call_count == 2


@patch("app.llm.agent._get_client")
def test_agent_returns_text_when_no_tool_needed(mock_get_client):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_text_response(
        "I'm not sure how to help with that."
    )
    mock_get_client.return_value = mock_client

    reply = agent_module.run_agent("what is the meaning of life?", S001)

    assert "not sure" in reply.lower()
    assert mock_client.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# tool_handlers — reorder_sku (uses real DB)
# ---------------------------------------------------------------------------

def test_reorder_sku_acknowledges_rather_than_deciding():
    # The decision now happens in the worker, so the DM reply cannot contain it.
    with TestClient(app):
        result = tool_handlers.reorder_sku(sku="WIDGET-42", quantity=10, seller=S001)
    assert "queued" in result.lower()
    assert "WIDGET-42" in result and "10" in result
    assert "MOCK-PO-" not in result


def test_reorder_sku_low_risk_outcome_is_posted_back_to_the_channel():
    # S001: 10 units * $8 = $80 — below auto-approve limits
    with patch("app.slack.client.send_message") as send_message:
        with TestClient(app):
            tool_handlers.reorder_sku(
                sku="WIDGET-42", quantity=10, seller=S001, reply_channel="C_DM_001"
            )
    channel, text, _token = send_message.call_args[0]
    assert channel == "C_DM_001"
    assert "✅" in text and "WIDGET-42" in text


def test_reorder_sku_high_risk_outcome_says_it_went_for_approval():
    # S001: 200 units * $8 = $1600 — above auto_approve_max_spend ($500)
    with patch("app.slack.client.send_message") as send_message:
        with TestClient(app):
            tool_handlers.reorder_sku(
                sku="WIDGET-42", quantity=200, seller=S001, reply_channel="C_DM_001"
            )
    _channel, text, _token = send_message.call_args[0]
    assert "approval" in text.lower()


def test_reorder_sku_without_a_channel_posts_nothing():
    # Platform-originated work has no conversation to answer.
    with patch("app.slack.client.send_message") as send_message:
        with TestClient(app):
            tool_handlers.reorder_sku(sku="WIDGET-42", quantity=10, seller=S001)
    assert not send_message.called


# ---------------------------------------------------------------------------
# tool_handlers — list_approvals (uses real DB)
# ---------------------------------------------------------------------------

def test_list_approvals_empty():
    with TestClient(app):
        result = tool_handlers.list_approvals(seller=S001)
    assert result == "No pending approvals."


def test_list_approvals_with_pending():
    with TestClient(app) as client:
        # Create a HIGH-risk event for S002 to generate a pending approval
        resp = client.post("/events", json={
            "seller_id": "S002",
            "event_type": "inventory_low",
            "payload": {"sku": "BULK-01", "current_quantity": 5},
        })
        client.get(f"/events/{resp.json()['event_id']}")  # wait for completion
        result = tool_handlers.list_approvals(seller=S002)
    assert "pending approval" in result.lower()
    assert "reorder_BULK-01" in result or "bulk-01" in result.lower() or "BULK-01" in result


# ---------------------------------------------------------------------------
# tool_handlers — get_refund_rate (uses real DB)
# ---------------------------------------------------------------------------

def test_get_refund_rate_no_data():
    with TestClient(app):
        result = tool_handlers.get_refund_rate(seller=S001)
    assert "no refund rate data" in result.lower()


def test_get_refund_rate_with_data():
    with TestClient(app) as client:
        client.post("/events", json={
            "seller_id": "S001",
            "event_type": "high_refund_rate_detected",
            "payload": {"refund_count": 5, "order_count": 100, "window_minutes": 1440},
        })
        result = tool_handlers.get_refund_rate(seller=S001)
    assert "5.0%" in result
    assert "5" in result and "100" in result


# ---------------------------------------------------------------------------
# policy engine — requested_quantity patch
# ---------------------------------------------------------------------------

def test_policy_uses_requested_quantity_from_payload():
    """Manual reorder quantity goes through the policy engine correctly."""
    from app.engine import policy as policy_engine
    from app.models.intent import Intent

    # S001 limit: 50 units / $500. Requesting 10 units → LOW risk
    result = policy_engine.evaluate(
        Intent.REORDER,
        S001,
        {"sku": "WIDGET-42", "requested_quantity": 10},
    )
    assert result.risk_level.value == "LOW"
    assert result.recommended_quantity == 10

    # Requesting 200 units → HIGH risk (above auto_approve_max_units=50)
    result = policy_engine.evaluate(
        Intent.REORDER,
        S001,
        {"sku": "WIDGET-42", "requested_quantity": 200},
    )
    assert result.risk_level.value == "HIGH"
    assert result.recommended_quantity == 200


def test_policy_falls_back_to_seller_default_when_no_requested_quantity():
    """Existing inventory_low events without requested_quantity still use policy default."""
    from app.engine import policy as policy_engine
    from app.models.intent import Intent

    result = policy_engine.evaluate(
        Intent.REORDER,
        S001,
        {"sku": "WIDGET-42", "current_quantity": 3},
    )
    # S001 default: reorder_quantity=40 → LOW risk (40 < 50 limit)
    assert result.recommended_quantity == 40
    assert result.risk_level.value == "LOW"
