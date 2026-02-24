from app.models.decision import PolicyResult, RiskLevel
from app.models.intent import Intent
from app.models.seller import Seller


def evaluate(intent: Intent, seller: Seller, payload: dict) -> PolicyResult:
    if intent == Intent.REORDER:
        return _evaluate_reorder(seller, payload)
    return PolicyResult(
        action="none",
        risk_level=RiskLevel.HIGH,
        reasoning=f"Unknown intent '{intent}' — escalating for human review.",
        recommended_quantity=0,
        estimated_spend=0.0,
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
