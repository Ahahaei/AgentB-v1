from app.models.decision import ExecutionResult, ExecutionStatus, PolicyResult, RiskLevel


def execute(policy_result: PolicyResult) -> ExecutionResult:
    if policy_result.risk_level == RiskLevel.LOW:
        return ExecutionResult(
            status=ExecutionStatus.EXECUTED,
            message=(
                f"[MOCK] Auto-executed: {policy_result.action} "
                f"({policy_result.recommended_quantity} units, "
                f"est. ${policy_result.estimated_spend:.2f})"
            ),
        )
    return ExecutionResult(
        status=ExecutionStatus.ESCALATED,
        message=(
            f"[MOCK] Escalated for approval: {policy_result.action} — "
            f"{policy_result.reasoning}"
        ),
    )
