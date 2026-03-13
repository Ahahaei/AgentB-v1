from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from app.db.engine import SessionLocal
from app.db.models import ApprovalRow, EventRow, SellerRow
from app.models.approval import ApprovalStatus, PendingApproval
from app.models.decision import DecisionResult
from app.models.event import EventRecord, EventStatus
from app.models.seller import Seller


@contextmanager
def _session():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _seller_from_row(row: SellerRow) -> Seller:
    return Seller.model_validate({
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "slack_channel_id": row.slack_channel_id,
        "policies": row.policies,
    })


def _event_from_row(row: EventRow) -> EventRecord:
    return EventRecord.model_validate({
        "id": row.id,
        "seller_id": row.seller_id,
        "event_type": row.event_type,
        "payload": row.payload,
        "status": row.status,
        "result": row.result,
        "error": row.error,
        "created_at": _ensure_utc(row.created_at),
        "updated_at": _ensure_utc(row.updated_at),
    })


def _approval_from_row(row: ApprovalRow) -> PendingApproval:
    return PendingApproval.model_validate({
        "id": row.id,
        "event_id": row.event_id,
        "seller_id": row.seller_id,
        "intent": row.intent,
        "policy_result": row.policy_result,
        "status": row.status,
        "created_at": _ensure_utc(row.created_at),
        "resolved_at": _ensure_utc(row.resolved_at),
        "resolved_by": row.resolved_by,
        "slack_channel_id": row.slack_channel_id,
        "slack_ts": row.slack_ts,
    })


# --- Seller ---

def get_seller(seller_id: str) -> Optional[Seller]:
    with _session() as db:
        row = db.get(SellerRow, seller_id)
        return _seller_from_row(row) if row else None


# --- Events ---

def create_event(record: EventRecord) -> None:
    with _session() as db:
        db.add(EventRow(
            id=record.id,
            seller_id=record.seller_id,
            event_type=record.event_type.value,
            payload=record.payload,
            status=record.status.value,
            result=None,
            error=None,
            created_at=record.created_at,
            updated_at=record.updated_at,
        ))


def get_event(event_id: str) -> Optional[EventRecord]:
    with _session() as db:
        row = db.get(EventRow, event_id)
        return _event_from_row(row) if row else None


def set_event_processing(event_id: str) -> None:
    with _session() as db:
        row = db.get(EventRow, event_id)
        row.status = EventStatus.PROCESSING.value
        row.updated_at = datetime.now(timezone.utc)


def set_event_completed(event_id: str, result: Optional[DecisionResult]) -> None:
    with _session() as db:
        row = db.get(EventRow, event_id)
        row.status = EventStatus.COMPLETED.value
        row.result = result.model_dump(mode="json") if result else None
        row.updated_at = datetime.now(timezone.utc)


def set_event_failed(event_id: str, error: str) -> None:
    with _session() as db:
        row = db.get(EventRow, event_id)
        row.status = EventStatus.FAILED.value
        row.error = error
        row.updated_at = datetime.now(timezone.utc)


# --- Approvals ---

def create_approval(record: PendingApproval) -> None:
    with _session() as db:
        db.add(ApprovalRow(
            id=record.id,
            event_id=record.event_id,
            seller_id=record.seller_id,
            intent=record.intent.value,
            policy_result=record.policy_result.model_dump(mode="json"),
            status=record.status.value,
            created_at=record.created_at,
            slack_channel_id=record.slack_channel_id,
        ))


def get_approval(approval_id: str) -> Optional[PendingApproval]:
    with _session() as db:
        row = db.get(ApprovalRow, approval_id)
        return _approval_from_row(row) if row else None


def resolve_approval(approval_id: str, status: ApprovalStatus, resolved_by: str) -> None:
    with _session() as db:
        row = db.get(ApprovalRow, approval_id)
        row.status = status.value
        row.resolved_at = datetime.now(timezone.utc)
        row.resolved_by = resolved_by


def set_approval_slack_ts(approval_id: str, ts: str) -> None:
    with _session() as db:
        row = db.get(ApprovalRow, approval_id)
        row.slack_ts = ts
