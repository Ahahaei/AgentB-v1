from app import store
from app.engine import classifier, executor
from app.engine import policy as policy_engine
from app.models.decision import DecisionResult
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

        intent = classifier.classify(record.event_type)
        policy_result = policy_engine.evaluate(intent, seller, record.payload)
        execution_result = executor.execute(policy_result)

        result = DecisionResult(
            intent=intent,
            policy_result=policy_result,
            execution_result=execution_result,
        )
        store.set_event_completed(event_id, result)

    except Exception as exc:
        store.set_event_failed(event_id, str(exc))
