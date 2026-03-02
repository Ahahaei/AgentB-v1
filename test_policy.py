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


# --- order_spike_detected ---
# S001: auto_approve_max_multiplier=2.0
# S002: auto_approve_max_multiplier=1.5

SPIKE_PAYLOAD_LOW = {"order_count": 20, "baseline_count": 12, "window_minutes": 60}
# multiplier = 20/12 = 1.67x — below S001 threshold (2.0) → LOW, above S002 threshold (1.5) → HIGH

SPIKE_PAYLOAD_HIGH = {"order_count": 30, "baseline_count": 12, "window_minutes": 60}
# multiplier = 30/12 = 2.5x — above both thresholds → HIGH for both sellers


def test_order_spike_within_threshold_is_low_risk():
    result = evaluate(Intent.FLAG_ORDER_SPIKE, SELLER_LOW, SPIKE_PAYLOAD_LOW)
    assert result.risk_level == RiskLevel.LOW


def test_order_spike_exceeds_threshold_is_high_risk():
    result = evaluate(Intent.FLAG_ORDER_SPIKE, SELLER_LOW, SPIKE_PAYLOAD_HIGH)
    assert result.risk_level == RiskLevel.HIGH


def test_order_spike_tighter_threshold_escalates_earlier():
    # S002 has max_multiplier=1.5, same payload (1.67x) → HIGH
    result = evaluate(Intent.FLAG_ORDER_SPIKE, SELLER_HIGH, SPIKE_PAYLOAD_LOW)
    assert result.risk_level == RiskLevel.HIGH


def test_order_spike_reasoning_includes_multiplier():
    result = evaluate(Intent.FLAG_ORDER_SPIKE, SELLER_LOW, SPIKE_PAYLOAD_LOW)
    assert "1.7x" in result.reasoning


def test_order_spike_has_no_quantity_or_spend():
    result = evaluate(Intent.FLAG_ORDER_SPIKE, SELLER_LOW, SPIKE_PAYLOAD_LOW)
    assert result.recommended_quantity is None
    assert result.estimated_spend is None


# --- high_refund_rate_detected ---
# S001: auto_approve_max_rate=0.10 (10%)
# S002: auto_approve_max_rate=0.05 (5%)

REFUND_PAYLOAD_LOW = {"refund_count": 5, "order_count": 100, "window_minutes": 1440}
# rate = 5% — below S001 threshold (10%) → LOW, below S002 threshold (5%) = equal → LOW (strict >)

REFUND_PAYLOAD_HIGH = {"refund_count": 15, "order_count": 100, "window_minutes": 1440}
# rate = 15% — above both thresholds → HIGH

REFUND_PAYLOAD_S002_HIGH = {"refund_count": 6, "order_count": 100, "window_minutes": 1440}
# rate = 6% — above S002 threshold (5%) → HIGH, below S001 (10%) → LOW


def test_refund_rate_within_threshold_is_low_risk():
    result = evaluate(Intent.FLAG_REFUND_RATE, SELLER_LOW, REFUND_PAYLOAD_LOW)
    assert result.risk_level == RiskLevel.LOW


def test_refund_rate_exceeds_threshold_is_high_risk():
    result = evaluate(Intent.FLAG_REFUND_RATE, SELLER_LOW, REFUND_PAYLOAD_HIGH)
    assert result.risk_level == RiskLevel.HIGH


def test_refund_rate_tighter_threshold_escalates_earlier():
    # S002 threshold is 5%; 6% rate → HIGH for S002, LOW for S001
    assert evaluate(Intent.FLAG_REFUND_RATE, SELLER_HIGH, REFUND_PAYLOAD_S002_HIGH).risk_level == RiskLevel.HIGH
    assert evaluate(Intent.FLAG_REFUND_RATE, SELLER_LOW, REFUND_PAYLOAD_S002_HIGH).risk_level == RiskLevel.LOW


def test_refund_rate_reasoning_includes_percentage():
    result = evaluate(Intent.FLAG_REFUND_RATE, SELLER_LOW, REFUND_PAYLOAD_LOW)
    assert "5.0%" in result.reasoning


def test_refund_rate_has_no_quantity_or_spend():
    result = evaluate(Intent.FLAG_REFUND_RATE, SELLER_LOW, REFUND_PAYLOAD_LOW)
    assert result.recommended_quantity is None
    assert result.estimated_spend is None
