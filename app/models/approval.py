from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.models.decision import PolicyResult
from app.models.intent import Intent


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PendingApproval(BaseModel):
    id: str
    event_id: str
    seller_id: str
    intent: Intent
    policy_result: PolicyResult
    status: ApprovalStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None  # "api", "slack", etc.
