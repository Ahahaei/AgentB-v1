from datetime import datetime, timezone
from typing import Optional

from app.mock.sellers import MOCK_SELLERS
from app.models.approval import ApprovalStatus, PendingApproval
from app.models.decision import DecisionResult
from app.models.event import EventRecord, EventStatus
from app.models.seller import Seller

_sellers: dict[str, Seller] = {s.id: s for s in MOCK_SELLERS}
_events: dict[str, EventRecord] = {}
_approvals: dict[str, PendingApproval] = {}


# --- Seller ---

def get_seller(seller_id: str) -> Optional[Seller]:
    return _sellers.get(seller_id)


# --- Events ---

def create_event(record: EventRecord) -> None:
    _events[record.id] = record


def get_event(event_id: str) -> Optional[EventRecord]:
    return _events.get(event_id)


def set_event_processing(event_id: str) -> None:
    record = _events[event_id]
    _events[event_id] = record.model_copy(update={
        "status": EventStatus.PROCESSING,
        "updated_at": datetime.now(timezone.utc),
    })


def set_event_completed(event_id: str, result: Optional[DecisionResult]) -> None:
    record = _events[event_id]
    _events[event_id] = record.model_copy(update={
        "status": EventStatus.COMPLETED,
        "result": result,
        "updated_at": datetime.now(timezone.utc),
    })


def set_event_failed(event_id: str, error: str) -> None:
    record = _events[event_id]
    _events[event_id] = record.model_copy(update={
        "status": EventStatus.FAILED,
        "error": error,
        "updated_at": datetime.now(timezone.utc),
    })


# --- Approvals ---

def create_approval(record: PendingApproval) -> None:
    _approvals[record.id] = record


def get_approval(approval_id: str) -> Optional[PendingApproval]:
    return _approvals.get(approval_id)


def resolve_approval(approval_id: str, status: ApprovalStatus, resolved_by: str) -> None:
    record = _approvals[approval_id]
    _approvals[approval_id] = record.model_copy(update={
        "status": status,
        "resolved_at": datetime.now(timezone.utc),
        "resolved_by": resolved_by,
    })


def set_approval_slack_ts(approval_id: str, ts: str) -> None:
    record = _approvals[approval_id]
    _approvals[approval_id] = record.model_copy(update={"slack_ts": ts})
