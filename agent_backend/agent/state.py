from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """Legacy state — kept for backward compatibility with existing graph.py."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_id: str
    session_id: str
    agent_type: str
    step_count: int
    is_final: bool


class MultiAgentState(TypedDict):
    """Supervisor-based multi-agent state."""

    # Message history — operator.add accumulates across nodes
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # Identity
    user_id: str
    session_id: str

    # User input
    user_query: str

    # Rewrite + Intent output
    rewritten_query: str
    intent: str          # "chitchat" | "pre_sales" | "after_sales"
    intent_reason: str

    # Supervisor output
    next_agent: str      # "chitchat" | "pre_sales" | "after_sales" | "finish"
    supervisor_reason: str

    # Cross-agent handoff
    handoff_to: str      # target agent name when handing off, else ""
    handoff_reason: str
    handoff_from: str    # agent name that initiated handoff

    # Control
    current_agent: str
    step_count: int
    handoff_count: int
    is_final: bool
