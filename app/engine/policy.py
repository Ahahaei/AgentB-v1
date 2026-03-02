from app.models.decision import PolicyResult, RiskLevel
from app.models.intent import Intent
from app.models.seller import Seller


def evaluate(intent: Intent, seller: Seller, payload: dict) -> PolicyResult:
    if intent == Intent.REORDER:
        return _evaluate_reorder(seller, payload)
    if intent == Intent.FLAG_ORDER_SPIKE:
        return _evaluate_order_spike(seller, payload)
    if intent == Intent.FLAG_REFUND_RATE:
        return _evaluate_refund_rate(seller, payload)
    return PolicyResult(
        action="none",
        risk_level=RiskLevel.HIGH,
        reasoning=f"Unknown intent '{intent}' — escalating for human review.",
    )


def _evaluate_reorder(seller: Seller, payload: dict) -> PolicyResult:
    pol = seller.policies.inventory_low
    qty = pol.reorder_quantity
    spend = qty * pol.unit_cost
    sku = payload.get("sku", "unknown")

    units_ok = qty <= pol.auto_approve_max_units
    spend_ok = spend <= pol.auto_approve_max_spend

    if units_ok and spend_ok:
        risk = RiskLevel.LOW
        reasoning = (
            f"Reorder {qty} units of {sku} at ${pol.unit_cost:.2f}/unit "
            f"(est. ${spend:.2f}) is within auto-approve limits "
            f"({pol.auto_approve_max_units} units / ${pol.auto_approve_max_spend:.2f})."
        )
    else:
        risk = RiskLevel.HIGH
        violations = []
        if not units_ok:
            violations.append(
                f"quantity {qty} exceeds limit {pol.auto_approve_max_units}"
            )
        if not spend_ok:
            violations.append(
                f"spend ${spend:.2f} exceeds limit ${pol.auto_approve_max_spend:.2f}"
            )
        reasoning = (
            f"Reorder {qty} units of {sku} at ${pol.unit_cost:.2f}/unit "
            f"(est. ${spend:.2f}) requires approval: {'; '.join(violations)}."
        )

    return PolicyResult(
        action=f"reorder_{sku}",
        risk_level=risk,
        reasoning=reasoning,
        recommended_quantity=qty,
        estimated_spend=spend,
    )


def _evaluate_order_spike(seller: Seller, payload: dict) -> PolicyResult:
    pol = seller.policies.order_spike
    order_count = payload.get("order_count", 0)
    baseline_count = payload.get("baseline_count", 1)
    window_minutes = payload.get("window_minutes", 60)

    multiplier = order_count / baseline_count if baseline_count > 0 else float("inf")

    if multiplier <= pol.auto_approve_max_multiplier:
        risk = RiskLevel.LOW
        reasoning = (
            f"Order spike of {multiplier:.1f}x baseline ({order_count} orders vs "
            f"{baseline_count} expected in {window_minutes}min) is within "
            f"auto-approve threshold ({pol.auto_approve_max_multiplier}x)."
        )
    else:
        risk = RiskLevel.HIGH
        reasoning = (
            f"Order spike of {multiplier:.1f}x baseline ({order_count} orders vs "
            f"{baseline_count} expected in {window_minutes}min) exceeds "
            f"auto-approve threshold ({pol.auto_approve_max_multiplier}x) — requires review."
        )

    return PolicyResult(
        action="flag_order_spike",
        risk_level=risk,
        reasoning=reasoning,
    )


def _evaluate_refund_rate(seller: Seller, payload: dict) -> PolicyResult:
    pol = seller.policies.high_refund_rate
    refund_count = payload.get("refund_count", 0)
    order_count = payload.get("order_count", 1)
    window_minutes = payload.get("window_minutes", 1440)

    rate = refund_count / order_count if order_count > 0 else 1.0
    rate_pct = rate * 100

    if rate <= pol.auto_approve_max_rate:
        risk = RiskLevel.LOW
        reasoning = (
            f"Refund rate of {rate_pct:.1f}% ({refund_count}/{order_count} orders "
            f"in {window_minutes}min) is within auto-approve threshold "
            f"({pol.auto_approve_max_rate * 100:.0f}%)."
        )
    else:
        risk = RiskLevel.HIGH
        reasoning = (
            f"Refund rate of {rate_pct:.1f}% ({refund_count}/{order_count} orders "
            f"in {window_minutes}min) exceeds auto-approve threshold "
            f"({pol.auto_approve_max_rate * 100:.0f}%) — requires review."
        )

    return PolicyResult(
        action="flag_refund_rate",
        risk_level=risk,
        reasoning=reasoning,
    )
