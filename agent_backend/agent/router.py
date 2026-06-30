"""Router agent (v1.7) — merged rewrite + intent + chitchat + supervisor into one node.

Single LLM call handles: query rewrite, intent classification, chitchat reply, and routing.
Fast-path skips LLM for obvious greetings. Handoff requests bypass LLM entirely.
"""

import json
import re
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agent_backend.agent.nodes import create_llm
from agent_backend.agent.prompts import ROUTER_PROMPT
from agent_backend.agent.state import MultiAgentState

logger = logging.getLogger(__name__)

# ── Fast-path keyword sets ────────────────────────────────────

_GREETING_WORDS = {"你好", "嗨", "在吗", "hello", "hi", "嘿", "早", "晚上好", "早上好", "下午好", "在不在", "哈喽"}

_GREETING_REPLIES = {
    "你好": "你好呀！有什么可以帮你的吗？可以帮你查活动、买票、查订单哦。",
    "嗨": "嗨！有什么可以帮你的？",
    "hello": "Hello! 有什么可以帮你的吗？",
    "hi": "Hi! 有什么可以帮你的？",
    "在吗": "在的！有什么可以帮你的吗？",
    "在不在": "在的！有什么可以帮你的吗？",
    "哈喽": "哈喽！有什么可以帮你的吗？",
    "早": "早上好！有什么可以帮你的吗？",
    "早上好": "早上好！有什么可以帮你的吗？",
    "晚上好": "晚上好！有什么可以帮你的吗？",
    "下午好": "下午好！有什么可以帮你的吗？",
    "嘿": "嘿！有什么可以帮你的？",
}


def _fast_path_greeting(text: str) -> str | None:
    """Return a greeting reply if the text is purely a greeting, else None."""
    t = text.strip()
    # Exact match
    if t in _GREETING_REPLIES:
        return _GREETING_REPLIES[t]
    # Prefix match (e.g. "你好啊" → "你好")
    for word in _GREETING_WORDS:
        if t == word or t.startswith(word):
            return _GREETING_REPLIES.get(word, "你好！有什么可以帮你的吗？")
    return None


async def router_node(state: MultiAgentState) -> dict:
    """Route the user query: fast-path greeting → direct reply, else LLM for rewrite+intent+routing.

    Sets: rewritten_query, intent, next_agent, messages (rewritten query or chitchat reply)
    """
    user_query = state.get("user_query", "").strip()

    # ── Fast path: pure greeting → direct reply, no LLM ──
    greeting_reply = _fast_path_greeting(user_query)
    if greeting_reply:
        return {
            "messages": [AIMessage(content=greeting_reply)],
            "rewritten_query": user_query,
            "intent": "chitchat",
            "intent_reason": "Fast path: greeting",
            "next_agent": "finish",
            "current_agent": "chitchat",
            "is_final": True,
        }

    # ── Handoff: unconditionally route to target agent, no LLM ──
    handoff_to = state.get("handoff_to", "")
    if handoff_to:
        return {
            "next_agent": handoff_to,
            "current_agent": handoff_to,
            "handoff_to": "",
            "handoff_reason": "",
            "handoff_from": "",
        }

    # ── Normal path: single LLM call for rewrite + intent + reply/routing ──
    llm = create_llm(fast=True)

    msgs = [SystemMessage(content=ROUTER_PROMPT)]
    # Include recent conversation context
    all_msgs = list(state.get("messages", []))
    for m in all_msgs[-6:]:
        msgs.append(m)
    msgs.append(HumanMessage(content=user_query))

    raw = await llm.ainvoke(msgs)
    text = str(raw.content) if raw.content else ""

    # ── Parse structured JSON output ──
    try:
        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            intent = data.get("intent", "chitchat")
            rewritten = data.get("rewritten_query", user_query)
            reply = data.get("reply")
            reason = data.get("reason", "")

            # Chitchat: router replies directly, graph ends
            if intent == "chitchat" and reply:
                return {
                    "messages": [AIMessage(content=str(reply))],
                    "rewritten_query": rewritten,
                    "intent": intent,
                    "intent_reason": reason,
                    "next_agent": "finish",
                    "current_agent": "chitchat",
                    "is_final": True,
                }

            # Pre-sales / after-sales: route to sub-agent with rewritten query
            return {
                "messages": [HumanMessage(content=rewritten)],
                "rewritten_query": rewritten,
                "intent": intent,
                "intent_reason": reason,
                "next_agent": intent,
                "current_agent": intent,
            }
    except Exception:
        logger.warning("Router JSON parse failed, fallback to chitchat")

    # ── Fallback ──
    return {
        "messages": [AIMessage(content="你好呀！有什么可以帮你的吗？")],
        "rewritten_query": user_query,
        "intent": "chitchat",
        "intent_reason": "Fallback",
        "next_agent": "finish",
        "current_agent": "chitchat",
        "is_final": True,
    }


def router_dispatch(state: MultiAgentState) -> str:
    """Conditional edge: read next_agent and return the graph target."""
    return state.get("next_agent", "finish")
