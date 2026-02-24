import pytest

from app.engine.policy import evaluate
from app.mock.sellers import MOCK_SELLERS
from app.models.decision import RiskLevel
from app.models.intent import Intent

SELLER_LOW = next(s for s in MOCK_SELLERS if s.id == "S001")   # 40 units * $8 = $320 → LOW
SELLER_HIGH = next(s for s in MOCK_SELLERS if s.id == "S002")  # 200 units * $5 = $1000 → HIGH

PAYLOAD = {"sku": "TEST-SKU", "current_quantity": 3}


def test_within_thresholds_is_low_risk():
    result = evaluate(Intent.REORDER, SELLER_LOW, PAYLOAD)
    assert result.risk_level == RiskLevel.LOW


def test_exceeds_thresholds_is_high_risk():
    result = evaluate(Intent.REORDER, SELLER_HIGH, PAYLOAD)
    assert result.risk_level == RiskLevel.HIGH


def test_recommended_quantity_matches_seller_policy():
    result = evaluate(Intent.REORDER, SELLER_LOW, PAYLOAD)
    assert result.recommended_quantity == SELLER_LOW.policies.inventory_low.reorder_quantity


def test_estimated_spend_is_quantity_times_unit_cost():
    pol = SELLER_LOW.policies.inventory_low
    result = evaluate(Intent.REORDER, SELLER_LOW, PAYLOAD)
    assert result.estimated_spend == pytest.approx(pol.reorder_quantity * pol.unit_cost)


def test_sku_appears_in_reasoning():
    result = evaluate(Intent.REORDER, SELLER_LOW, PAYLOAD)
    assert "TEST-SKU" in result.reasoning


def test_high_risk_reasoning_names_violations():
    result = evaluate(Intent.REORDER, SELLER_HIGH, PAYLOAD)
    assert "exceeds" in result.reasoning
