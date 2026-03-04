from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.models.intent import Intent


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PolicyResult(BaseModel):
    action: str
    risk_level: RiskLevel
    reasoning: str
    recommended_quantity: Optional[int] = None
    estimated_spend: Optional[float] = None


class ExecutionStatus(str, Enum):
    EXECUTED = "executed"
    ESCALATED = "escalated"


class ExecutionResult(BaseModel):
    status: ExecutionStatus
    message: str
    approval_id: Optional[str] = None


class DecisionResult(BaseModel):
    intent: Intent
    policy_result: PolicyResult
    execution_result: ExecutionResult
