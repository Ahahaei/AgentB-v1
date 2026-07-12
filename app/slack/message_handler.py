import logging

from app.llm.agent import run_agent
from app.models.seller import Seller
from app.slack import client as slack_client

logger = logging.getLogger(__name__)


def handle_message(seller: Seller, message_text: str, channel: str) -> None:
    """
    Entry point for conversational Slack messages.
    Calls the LLM agent, then posts the response back to the sender's channel.
    """
    logger.info(
        "seller=%s channel=%s message=%r", seller.id, channel, message_text
    )
    try:
        response = run_agent(message_text, seller)
    except Exception:
        logger.exception("seller=%s agent failed", seller.id)
        response = "Something went wrong. Please try again."

    bot_token = seller.slack_credentials.bot_token
    slack_client.send_message(channel, response, bot_token)
