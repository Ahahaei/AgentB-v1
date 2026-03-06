import hashlib
import hmac
import json
import os
import time
import urllib.parse

from fastapi import APIRouter, HTTPException, Request

from app import store
from app.models.approval import ApprovalStatus
from app.slack import client as slack_client

router = APIRouter(prefix="/slack", tags=["slack"])


def _verify_signature(body: bytes, timestamp: str, signature: str) -> bool:
    # Reject requests older than 5 minutes (replay attack prevention)
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return False

    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    sig_base = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        signing_secret.encode(), sig_base.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/interactions")
async def handle_interaction(request: Request):
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not _verify_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Slack sends application/x-www-form-urlencoded with a JSON 'payload' field
    form = urllib.parse.parse_qs(body.decode())
    payload = json.loads(form["payload"][0])

    action = payload["actions"][0]
    action_id = action["action_id"]
    approval_id = action["value"]
    slack_user_id = payload["user"]["id"]

    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Approval '{approval_id}' is already {approval.status.value}",
        )

    if action_id == "approve_action":
        new_status = ApprovalStatus.APPROVED
        resolution_text = f"✅ Approved by <@{slack_user_id}>"
    elif action_id == "reject_action":
        new_status = ApprovalStatus.REJECTED
        resolution_text = f"❌ Rejected by <@{slack_user_id}>"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_id}")

    store.resolve_approval(approval_id, new_status, resolved_by=slack_user_id)

    # Update the original Slack message to replace buttons with resolution text
    updated = store.get_approval(approval_id)
    if updated.slack_channel_id and updated.slack_ts:
        slack_client.update_message(updated.slack_channel_id, updated.slack_ts, resolution_text)

    return {"ok": True}
