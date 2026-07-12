import logging
import os

from anthropic import Anthropic

from app.llm import tool_handlers
from app.llm.tools import TOOLS
from app.models.seller import Seller

logger = logging.getLogger(__name__)

_FALLBACK = (
    "I'm not sure how to help with that. Try:\n"
    "• \"Reorder 50 units of WIDGET-42\"\n"
    "• \"Show my pending approvals\"\n"
    "• \"What is my refund rate?\""
)

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _client


def _system_prompt(seller: Seller) -> str:
    return (
        f"You are an operations assistant for {seller.name}, an e-commerce seller. "
        "You help manage day-to-day operations via Slack. "
        "Use the available tools to handle requests. "
        "All execution decisions are made by a deterministic policy engine — "
        "you extract intent and parameters only, never make execution calls yourself. "
        "Be concise. This is Slack."
    )


def _dispatch(tool_name: str, tool_input: dict, seller: Seller) -> str:
    if tool_name == "reorder_sku":
        return tool_handlers.reorder_sku(
            sku=tool_input["sku"],
            quantity=tool_input["quantity"],
            seller=seller,
        )
    if tool_name == "list_approvals":
        return tool_handlers.list_approvals(seller=seller)
    if tool_name == "get_refund_rate":
        return tool_handlers.get_refund_rate(seller=seller)
    return f"Unknown tool: {tool_name}"


def run_agent(message_text: str, seller: Seller) -> str:
    """
    Run the tool-calling agent for a single Slack message.

    Turn 1: send message to Claude with tools defined.
    If Claude picks a tool: run it, feed result back, get final text response.
    If Claude responds with plain text: return it directly.
    """
    model = os.environ.get("LLM_MODEL", "claude-haiku-4-5")
    client = _get_client()
    system = _system_prompt(seller)
    messages = [{"role": "user", "content": message_text}]

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        tools=TOOLS,
        messages=messages,
    )
    logger.info("seller=%s stop_reason=%s", seller.id, response.stop_reason)

    if response.stop_reason == "end_turn":
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return _FALLBACK

    if response.stop_reason == "tool_use":
        tool_block = next(b for b in response.content if b.type == "tool_use")
        logger.info(
            "seller=%s tool=%s input=%s", seller.id, tool_block.name, tool_block.input
        )

        tool_result = _dispatch(tool_block.name, tool_block.input, seller)
        logger.info("seller=%s tool_result=%r", seller.id, tool_result)

        # Send tool result back to Claude for a natural language response
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": tool_result,
            }],
        })

        followup = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        for block in followup.content:
            if hasattr(block, "text"):
                return block.text

    return _FALLBACK
