"""Supervisor routing node — LLM-based router that decides which agent to invoke."""

import json
import re
import logging
from langchain_core.messages import SystemMessage

from agent_backend.agent.nodes import create_llm
from agent_backend.agent.prompts import SUPERVISOR_PROMPT
from agent_backend.agent.state import MultiAgentState

logger = logging.getLogger(__name__)


async def supervisor_node(state: MultiAgentState) -> dict:
    """Decide which agent handles the current turn.

    Reads: intent, handoff_to, messages
    Sets: next_agent, supervisor_reason, current_agent
    """
    llm = create_llm()

    # Build context for supervisor
    context_lines = [
        f"Classified intent: {state.get('intent', 'unknown')}",
        f"Intent reason: {state.get('intent_reason', '')}",
    ]

    if state.get("handoff_to"):
        context_lines.append(
            f"HANDOFF REQUESTED: from {state.get('handoff_from', '?')} "
            f"to {state.get('handoff_to', '?')}. "
            f"Reason: {state.get('handoff_reason', '')}"
        )

    messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
        SystemMessage(content="\n".join(context_lines)),
    ]
    # Include last few messages for context
    all_msgs = list(state.get("messages", []))
    for m in all_msgs[-4:]:
        messages.append(m)

    raw = await llm.ainvoke(messages)
    text = str(raw.content) if raw.content else ""

    # Parse structured output
    try:
        json_match = re.search(r'\{[^{}]*"next_agent"[^{}]*"reason"[^{}]*\}', text, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            next_agent = data.get("next_agent", "finish")
        else:
            next_agent = _derive_from_intent(state)
    except (json.JSONDecodeError, KeyError):
        next_agent = _derive_from_intent(state)

    # If handoff is explicitly requested, honor it unconditionally
    if state.get("handoff_to"):
        next_agent = state["handoff_to"]

    return {
        "next_agent": next_agent,
        "supervisor_reason": f"Routing to {next_agent}",
        "current_agent": next_agent,
        # Clear handoff flags after supervisor processes them
        "handoff_to": "",
        "handoff_reason": "",
        "handoff_from": "",
    }


def _derive_from_intent(state: MultiAgentState) -> str:
    """Simple fallback: follow classified intent."""
    intent = state.get("intent", "chitchat")
    if intent in ("chitchat", "pre_sales", "after_sales"):
        return intent
    return "chitchat"


def _supervisor_dispatch(state: MultiAgentState) -> str:
    """Conditional edge function: read next_agent and return the target."""
    return state.get("next_agent", "finish")
