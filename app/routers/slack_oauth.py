import json
import logging
import os
import urllib.parse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app import store
from app.models.seller import SlackCredentials

router = APIRouter(prefix="/slack", tags=["slack-oauth"])
logger = logging.getLogger(__name__)

_SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
_SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"

# Scopes required for the bot
_BOT_SCOPES = "chat:write,channels:history,im:history,im:write"


@router.get("/authorize")
def authorize(seller_id: str, channel_id: str):
    """Redirect the seller's browser to Slack's OAuth consent screen."""
    client_id = os.environ.get("SLACK_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=500, detail="SLACK_CLIENT_ID is not configured")

    seller = store.get_seller(seller_id)
    if seller is None:
        raise HTTPException(status_code=404, detail=f"Seller '{seller_id}' not found")

    state = urllib.parse.quote(json.dumps({"seller_id": seller_id, "channel_id": channel_id}))
    redirect_uri = os.environ.get("SLACK_REDIRECT_URI", "")

    params = {
        "client_id": client_id,
        "scope": _BOT_SCOPES,
        "state": state,
    }
    if redirect_uri:
        params["redirect_uri"] = redirect_uri

    url = f"{_SLACK_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url)


@router.get("/callback")
async def callback(code: str, state: str):
    """Exchange the OAuth code for a bot token and persist it on the seller."""
    client_id = os.environ.get("SLACK_CLIENT_ID", "")
    client_secret = os.environ.get("SLACK_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="SLACK_CLIENT_ID / SLACK_CLIENT_SECRET not configured")

    try:
        state_data = json.loads(urllib.parse.unquote(state))
        seller_id = state_data["seller_id"]
        channel_id = state_data["channel_id"]
    except (KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    seller = store.get_seller(seller_id)
    if seller is None:
        raise HTTPException(status_code=404, detail=f"Seller '{seller_id}' not found")

    redirect_uri = os.environ.get("SLACK_REDIRECT_URI", "")
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }
    if redirect_uri:
        payload["redirect_uri"] = redirect_uri

    async with httpx.AsyncClient() as http:
        resp = await http.post(_SLACK_TOKEN_URL, data=payload)

    data = resp.json()
    if not data.get("ok"):
        logger.error("slack oauth.v2.access error: %s", data.get("error"))
        raise HTTPException(status_code=400, detail=f"Slack OAuth error: {data.get('error')}")

    bot_token = data["access_token"]
    credentials = SlackCredentials(bot_token=bot_token)
    updates: dict = {
        "slack_credentials": credentials.model_dump(mode="json"),
        "slack_channel_id": channel_id,
    }

    # Capture the Slack user ID of whoever authorized the app and link them to this seller
    authed_user_id = data.get("authed_user", {}).get("id")
    if authed_user_id:
        updates["slack_user_id"] = authed_user_id

    store.update_seller(seller_id, updates)

    logger.info("slack oauth complete seller=%s channel=%s authed_user=%s", seller_id, channel_id, authed_user_id)
    return {"ok": True, "seller_id": seller_id, "channel_id": channel_id}
