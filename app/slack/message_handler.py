import logging

from app.models.seller import Seller

logger = logging.getLogger(__name__)


def handle_message(seller: Seller, message_text: str, channel: str) -> None:
    """
    Entry point for conversational Slack messages.

    Phase 3 replaces this stub with the LLM tool-calling agent.
    The seller is already resolved and active at this point.
    """
    logger.info(
        "Received message from seller %s (channel=%s): %r",
        seller.id,
        channel,
        message_text,
    )
