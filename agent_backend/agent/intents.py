"""Rewrite + intent classification node — the first node in the graph."""

import json
import re
import logging
from langchain_core.messages import SystemMessage

from agent_backend.agent.nodes import create_llm
from agent_backend.agent.prompts import REWRITE_INTENT_PROMPT
from agent_backend.agent.state import MultiAgentState

logger = logging.getLogger(__name__)


async def rewrite_intent_node(state: MultiAgentState) -> dict:
    """Rewrite user query and classify intent via a single structured LLM call.

    Sets: rewritten_query, intent, intent_reason
    """
    llm = create_llm()

    messages = [
        SystemMessage(content=REWRITE_INTENT_PROMPT),
    ]
    # Include recent conversation context for pronoun resolution (last 6 msgs)
    all_msgs = list(state.get("messages", []))
    for m in all_msgs[-6:]:
        messages.append(m)

    raw = await llm.ainvoke(messages)
    text = str(raw.content) if raw.content else ""

    # Try structured output first, fall back to regex parsing
    try:
        # Extract JSON block from response
        json_match = re.search(r'\{[^{}]*"rewritten_query"[^{}]*"intent"[^{}]*"reason"[^{}]*\}', text, re.DOTALL)
        if not json_match:
            # Try broader match
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "rewritten_query": data.get("rewritten_query", state.get("user_query", "")),
                "intent": _validate_intent(data.get("intent", "chitchat")),
                "intent_reason": data.get("reason", ""),
            }
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Structured output parse failed: {e}, falling back to heuristic")

    # Heuristic fallback
    intent = _heuristic_classify(state.get("user_query", ""))
    return {
        "rewritten_query": state.get("user_query", ""),
        "intent": intent,
        "intent_reason": f"Fallback heuristic classification: {intent}",
    }


def _validate_intent(intent: str) -> str:
    valid = {"chitchat", "pre_sales", "after_sales"}
    intent = intent.strip().lower()
    if intent in valid:
        return intent
    # Map legacy types
    if intent in ("ticket",):
        return "pre_sales"
    if intent in ("customer_service",):
        return "after_sales"
    if intent in ("general",):
        return "pre_sales"
    return "chitchat"


def _heuristic_classify(text: str) -> str:
    """Simple keyword-based fallback classification."""
    text_lower = text.lower()

    pre_sales_kw = ["活动", "演出", "晚会", "比赛", "买票", "购票", "下单", "场馆", "票价",
                    "推荐", "热卖", "好看的", "有什么", "搜索", "订票"]
    after_sales_kw = ["订单", "退款", "退票", "售后", "投诉", "购票记录", "我的票",
                      "订单状态", "改签", "我的订单"]

    pre_score = sum(1 for kw in pre_sales_kw if kw in text_lower)
    after_score = sum(1 for kw in after_sales_kw if kw in text_lower)

    if pre_score > after_score:
        return "pre_sales"
    elif after_score > pre_score:
        return "after_sales"
    else:
        return "chitchat"
