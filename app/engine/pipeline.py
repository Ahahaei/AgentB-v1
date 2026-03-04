import uuid
from datetime import datetime, timezone

from app import store
from app.engine import classifier, executor
from app.engine import policy as policy_engine
from app.models.approval import ApprovalStatus, PendingApproval
from app.models.decision import DecisionResult, ExecutionStatus
from app.models.event import EVENT_LAYER_MAP, EventLayer
from app.models.seller import SellerStatus


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
        policy_result = policy_engine.evaluate(intent, seller, record.payload)
        execution_result = executor.execute(policy_result)

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
            )
            store.create_approval(approval)
            execution_result = execution_result.model_copy(update={"approval_id": approval_id})

        result = DecisionResult(
            intent=intent,
            policy_result=policy_result,
            execution_result=execution_result,
        )
        store.set_event_completed(event_id, result)

    except Exception as exc:
        store.set_event_failed(event_id, str(exc))
