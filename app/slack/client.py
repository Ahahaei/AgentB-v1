import os

from slack_sdk import WebClient

from app.models.approval import PendingApproval


def _get_client() -> WebClient:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is not set")
    return WebClient(token=token)


def _build_blocks(approval: PendingApproval, seller_name: str) -> list[dict]:
    pr = approval.policy_result
    intent_label = approval.intent.value.replace("_", " ").title()

    fields = [
        {"type": "mrkdwn", "text": f"*Seller:* {seller_name} ({approval.seller_id})"},
        {"type": "mrkdwn", "text": f"*Risk:* {pr.risk_level.value}"},
        {"type": "mrkdwn", "text": f"*Action:* {pr.action}"},
    ]
    if pr.recommended_quantity is not None:
        fields.append({"type": "mrkdwn", "text": f"*Quantity:* {pr.recommended_quantity} units"})
    if pr.estimated_spend is not None:
        fields.append({"type": "mrkdwn", "text": f"*Est. Spend:* ${pr.estimated_spend:,.2f}"})

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"⚠️ Escalation: {intent_label}"},
        },
        {
            "type": "section",
            "fields": fields,
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Reasoning:* {pr.reasoning}"},
        },
        {
            "type": "actions",
            "block_id": "approval_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "value": approval.id,
                    "action_id": "approve_action",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "value": approval.id,
                    "action_id": "reject_action",
                },
            ],
        },
    ]


def send_approval_request(approval: PendingApproval, seller_name: str) -> str:
    """Post an escalation message with Approve/Reject buttons. Returns the message ts."""
    client = _get_client()
    intent_label = approval.intent.value.replace("_", " ").title()
    resp = client.chat_postMessage(
        channel=approval.slack_channel_id,
        text=f"⚠️ Escalation: {intent_label} for {seller_name}",
        blocks=_build_blocks(approval, seller_name),
    )
    return resp["ts"]


def update_message(channel_id: str, ts: str, text: str) -> None:
    """Replace the original escalation message content (removes buttons)."""
    client = _get_client()
    client.chat_update(
        channel=channel_id,
        ts=ts,
        text=text,
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
    )
