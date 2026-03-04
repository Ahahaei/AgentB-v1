from fastapi import APIRouter, HTTPException

from app import store
from app.models.approval import ApprovalStatus

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/{approval_id}")
def get_approval(approval_id: str):
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
    return approval


@router.post("/{approval_id}/approve")
def approve_approval(approval_id: str):
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Approval '{approval_id}' is already {approval.status.value}",
        )
    store.resolve_approval(approval_id, ApprovalStatus.APPROVED, resolved_by="api")
    return store.get_approval(approval_id)


@router.post("/{approval_id}/reject")
def reject_approval(approval_id: str):
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Approval '{approval_id}' is already {approval.status.value}",
        )
    store.resolve_approval(approval_id, ApprovalStatus.REJECTED, resolved_by="api")
    return store.get_approval(approval_id)
