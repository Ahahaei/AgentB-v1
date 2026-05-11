import hashlib
import hmac
import json
import os
import time
import urllib.parse

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app import store
from app.engine.pipeline import execute_approved
from app.models.approval import ApprovalStatus
from app.slack import client as slack_client
from app.slack.message_handler import handle_message

router = APIRouter(prefix="/slack", tags=["slack"])

# In-process deduplication: Slack retries on non-2xx or timeouts.
# Storing seen event_ids prevents double-processing within a process lifetime.
_seen_event_ids: set[str] = set()


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
        resolution_text = f"✅ Approved by <@{slack_user_id}>"
        execute_approved(approval_id, resolved_by=slack_user_id)
    elif action_id == "reject_action":
        resolution_text = f"❌ Rejected by <@{slack_user_id}>"
        store.resolve_approval(approval_id, ApprovalStatus.REJECTED, resolved_by=slack_user_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_id}")

    # Update the original Slack message to replace buttons with resolution text
    updated = store.get_approval(approval_id)
    if updated.slack_channel_id and updated.slack_ts:
        slack_client.update_message(updated.slack_channel_id, updated.slack_ts, resolution_text)

    return {"ok": True}


@router.post("/events")
async def handle_event(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not _verify_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    data = json.loads(body)

    # One-time URL verification handshake when registering the endpoint in Slack
    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}

    if data.get("type") != "event_callback":
        return {"ok": True}

    event = data.get("event", {})

    # Ignore bot messages (including messages the bot itself sends)
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"ok": True}

    # Only handle plain text messages
    if event.get("type") != "message" or not event.get("text"):
        return {"ok": True}

    # Deduplication: Slack retries if it doesn't receive a timely 2xx response
    event_id = data.get("event_id", "")
    if event_id in _seen_event_ids:
        return {"ok": True}
    _seen_event_ids.add(event_id)

    slack_user_id = event.get("user", "")
    message_text = event.get("text", "").strip()
    channel = event.get("channel", "")

    # Resolve seller — unknown users are silently dropped (don't let Slack retry)
    seller = store.get_seller_by_slack_user_id(slack_user_id)
    if seller is None:
        return {"ok": True}

    background_tasks.add_task(handle_message, seller, message_text, channel)
    return {"ok": True}
