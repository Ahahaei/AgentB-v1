import logging
from typing import Optional

from app import store
from app.models.event import EventType
from app.models.seller import Seller

logger = logging.getLogger(__name__)


def reorder_sku(
    sku: str,
    quantity: int,
    seller: Seller,
    reply_channel: Optional[str] = None,
) -> str:
    """
    Queue a manual reorder for the pipeline.

    Entry 2 of the ingest diagram: the same event + job insert pair the platform
    route performs. The decision happens later, in the worker — so this returns
    an acknowledgement, and `reply_channel` is how the outcome finds its way
    back to this conversation.
    """
    store.ingest_internal_event(
        seller.id,
        EventType.INVENTORY_LOW,
        {
            "sku": sku,
            "current_quantity": 0,
            # requested_quantity overrides the seller's default reorder_quantity in the policy engine
            "requested_quantity": quantity,
            "reply_channel": reply_channel,
        },
    )
    return (
        f"Queued: {quantity} units of {sku}. "
        f"The policy engine is evaluating it — I'll confirm here when it's decided."
    )


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
