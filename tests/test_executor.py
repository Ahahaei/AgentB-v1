from app.engine.executor import execute
from app.models.decision import ExecutionStatus, PolicyResult, RiskLevel


def _make_policy_result(risk: RiskLevel) -> PolicyResult:
    return PolicyResult(
        action="reorder_TEST-SKU",
        risk_level=risk,
        reasoning="test reasoning",
        recommended_quantity=40,
        estimated_spend=320.0,
    )


def test_low_risk_is_auto_executed():
    result = execute(_make_policy_result(RiskLevel.LOW))
    assert result.status == ExecutionStatus.EXECUTED
    assert "[MOCK]" in result.message


def test_high_risk_is_escalated():
    result = execute(_make_policy_result(RiskLevel.HIGH))
    assert result.status == ExecutionStatus.ESCALATED
    assert "[MOCK]" in result.message


def test_executed_message_includes_action():
    result = execute(_make_policy_result(RiskLevel.LOW))
    assert "reorder_TEST-SKU" in result.message


def test_escalated_message_includes_action():
    result = execute(_make_policy_result(RiskLevel.HIGH))
    assert "reorder_TEST-SKU" in result.message
