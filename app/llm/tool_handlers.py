import logging
import uuid
from datetime import datetime, timezone

from app import store
from app.engine.pipeline import run_pipeline
from app.models.decision import ExecutionStatus
from app.models.event import EventRecord, EventStatus, EventType
from app.models.seller import Seller

logger = logging.getLogger(__name__)


def reorder_sku(sku: str, quantity: int, seller: Seller) -> str:
    """
    Inject a manual reorder into the pipeline.
    The policy engine evaluates it against the seller's thresholds — auto-execute or escalate.
    """
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    record = EventRecord(
        id=event_id,
        seller_id=seller.id,
        event_type=EventType.INVENTORY_LOW,
        # requested_quantity overrides the seller's default reorder_quantity in the policy engine
        payload={"sku": sku, "current_quantity": 0, "requested_quantity": quantity},
        status=EventStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    store.create_event(record)
    run_pipeline(event_id)

    event = store.get_event(event_id)
    if event.status == EventStatus.FAILED:
        return f"Failed to process reorder: {event.error}"

    result = event.result
    execution_status = result.execution_result.status

    if execution_status == ExecutionStatus.EXECUTED:
        sp_result = result.execution_result.sp_api_result or {}
        order_id = sp_result.get("order_id", "N/A")
        spend = result.policy_result.estimated_spend
        return (
            f"Reorder submitted: {quantity} units of {sku}. "
            f"Order ID: {order_id}. Est. spend: ${spend:,.2f}."
        )

    if execution_status == ExecutionStatus.ESCALATED:
        spend = result.policy_result.estimated_spend
        return (
            f"Reorder of {quantity} units of {sku} (est. ${spend:,.2f}) "
            f"exceeds auto-approve limits — sent to your channel for approval."
        )

    return "Reorder processed."


def list_approvals(seller: Seller) -> str:
    """Return a formatted list of pending approvals for this seller."""
    approvals = store.get_pending_approvals_for_seller(seller.id)
    if not approvals:
        return "No pending approvals."

    lines = [f"{len(approvals)} pending approval(s):"]
    for a in approvals:
        pr = a.policy_result
        spend_part = f" — est. ${pr.estimated_spend:,.2f}" if pr.estimated_spend else ""
        lines.append(f"• {pr.action}{spend_part} (ID: {a.id[:8]}...)")
    return "\n".join(lines)


def get_refund_rate(seller: Seller) -> str:
    """Return the most recently recorded refund rate for this seller."""
    events = store.get_recent_events_by_type(
        seller.id, EventType.HIGH_REFUND_RATE_DETECTED, limit=1
    )
    if not events:
        return "No refund rate data recorded yet."

    payload = events[0].payload
    refund_count = payload.get("refund_count", 0)
    order_count = payload.get("order_count", 1)
    rate = (refund_count / order_count * 100) if order_count > 0 else 0.0
    window = payload.get("window_minutes", 1440)
    return (
        f"Refund rate: {rate:.1f}% "
        f"({refund_count} refunds / {order_count} orders in last {window} min)."
    )
