import logging
import uuid
from datetime import datetime, timezone

from app import store

logger = logging.getLogger(__name__)
from app.engine import classifier, executor
from app.engine import policy as policy_engine
from app.models.approval import ApprovalStatus, PendingApproval
from app.models.decision import DecisionResult, ExecutionStatus
from app.models.event import EVENT_LAYER_MAP, EventLayer
from app.models.seller import SellerStatus


def _outcome_message(record, result: DecisionResult) -> str:
    """What the seller reads in Slack once their DM request has been decided."""
    policy = result.policy_result
    sku = record.payload.get("sku", "the item")
    quantity = policy.recommended_quantity
    spend = f" (est. ${policy.estimated_spend:,.2f})" if policy.estimated_spend else ""

    if result.execution_result.status == ExecutionStatus.ESCALATED:
        return (
            f"⏳ {quantity} units of {sku}{spend} exceeds your auto-approve limits — "
            f"sent to your channel for approval."
        )
    return f"✅ {quantity} units of {sku}{spend} — done."


def _reply_to_chat(record, seller, result: DecisionResult) -> None:
    """Post the outcome back to the DM that asked for it.

    A chat request is acknowledged immediately and decided later in the worker,
    so the answer has to find its own way back. `reply_channel` is set only by
    the chat entry point; platform-originated events have none and stay silent.
    """
    channel = record.payload.get("reply_channel")
    if not channel or seller.slack_credentials is None:
        return
    from app.slack import client as slack_client
    try:
        slack_client.send_message(
            channel, _outcome_message(record, result), seller.slack_credentials.bot_token
        )
    except Exception:
        # The decision is already committed; a failed courtesy message must not
        # fail the job and trigger a retry of the work itself.
        logger.exception("event=%s failed to post outcome to channel=%s", record.id, channel)


def execute_approved(approval_id: str, resolved_by: str) -> None:
    store.resolve_approval(approval_id, ApprovalStatus.APPROVED, resolved_by=resolved_by)
    approval = store.get_approval(approval_id)
    event = store.get_event(approval.event_id)
    seller = store.get_seller(approval.seller_id)
    logger.info("approval=%s approved by %s — executing intent=%s", approval_id, resolved_by, approval.intent)
    from app.platforms.amazon import client as sp_api_client
    sp_result = sp_api_client.execute_intent(
        approval.intent,
        seller,
        event.payload,
        approval.policy_result,
    )
    store.set_event_sp_api_result(approval.event_id, sp_result)
    logger.info("approval=%s sp_api_result=%s", approval_id, sp_result)


def run_pipeline(event_id: str) -> None:
    store.set_event_processing(event_id)
    try:
        record = store.get_event(event_id)
        if record is None:
            raise ValueError(f"Event '{event_id}' not found in store")

        seller = store.get_seller(record.seller_id)
        if seller is None:
            raise ValueError(f"Seller '{record.seller_id}' not found")

        if seller.status != SellerStatus.ACTIVE:
            raise ValueError(
                f"Seller '{record.seller_id}' is not active (status: {seller.status.value})"
            )

        layer = EVENT_LAYER_MAP[record.event_type]

        if layer == EventLayer.DOMAIN:
            # Layer 1 — record the fact, no decision needed
            store.set_event_completed(event_id, result=None)
            return

        # Layer 2 — full decision pipeline
        intent = classifier.classify(record.event_type)
        logger.info("event=%s seller=%s intent=%s", event_id, record.seller_id, intent)
        policy_result = policy_engine.evaluate(intent, seller, record.payload)
        logger.info("event=%s risk=%s action=%s", event_id, policy_result.risk_level, policy_result.action)
        execution_result = executor.execute(policy_result)

        if execution_result.status == ExecutionStatus.EXECUTED:
            from app.platforms.amazon import client as sp_api_client
            sp_result = sp_api_client.execute_intent(intent, seller, record.payload, policy_result)
            execution_result = execution_result.model_copy(update={"sp_api_result": sp_result})
            logger.info("event=%s auto-executed sp_result=%s", event_id, sp_result)

        if execution_result.status == ExecutionStatus.ESCALATED:
            approval_id = str(uuid.uuid4())
            approval = PendingApproval(
                id=approval_id,
                event_id=event_id,
                seller_id=record.seller_id,
                intent=intent,
                policy_result=policy_result,
                status=ApprovalStatus.PENDING,
                created_at=datetime.now(timezone.utc),
                slack_channel_id=seller.slack_channel_id,
            )
            store.create_approval(approval)
            execution_result = execution_result.model_copy(update={"approval_id": approval_id})

            if seller.slack_credentials is not None:
                from app.slack import client as slack_client
                ts = slack_client.send_approval_request(approval, seller.name, seller.slack_credentials.bot_token)
                store.set_approval_slack_ts(approval_id, ts)

        result = DecisionResult(
            intent=intent,
            policy_result=policy_result,
            execution_result=execution_result,
        )
        store.set_event_completed(event_id, result)
        _reply_to_chat(record, seller, result)

    except Exception as exc:
        logger.exception("event=%s pipeline failed: %s", event_id, exc)
        store.set_event_failed(event_id, str(exc))
