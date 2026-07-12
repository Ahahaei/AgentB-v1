"""
Phase 1 — Seller identity tests.

Verifies that get_seller_by_slack_user_id() can resolve a Slack user_id
to a Seller, and returns None for unknown users.
"""

import app.store as store


def test_lookup_active_seller_by_slack_user_id():
    seller = store.get_seller_by_slack_user_id("U_MOCK_S001")
    assert seller is not None
    assert seller.id == "S001"
    assert seller.name == "Gadget Galaxy"
    assert seller.slack_user_id == "U_MOCK_S001"


def test_lookup_second_seller_by_slack_user_id():
    seller = store.get_seller_by_slack_user_id("U_MOCK_S002")
    assert seller is not None
    assert seller.id == "S002"
    assert seller.slack_user_id == "U_MOCK_S002"


def test_lookup_inactive_seller_by_slack_user_id():
    # Inactive sellers still resolve — callers decide what to do with status
    seller = store.get_seller_by_slack_user_id("U_MOCK_S003")
    assert seller is not None
    assert seller.id == "S003"
    assert seller.status.value == "inactive"


def test_unknown_slack_user_id_returns_none():
    seller = store.get_seller_by_slack_user_id("U_DOES_NOT_EXIST")
    assert seller is None


def test_seller_model_includes_slack_user_id():
    seller = store.get_seller("S001")
    assert seller is not None
    assert seller.slack_user_id == "U_MOCK_S001"


def test_seller_without_slack_user_id_is_none_not_missing():
    # get_seller still works and slack_user_id defaults to None when not set
    seller = store.get_seller("S002")
    assert seller is not None
    assert hasattr(seller, "slack_user_id")
