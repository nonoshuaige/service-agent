"""Chitchat agent — no tools, handles casual conversation directly."""

from agent_backend.agent.state import MultiAgentState
from agent_backend.agent.prompts import CHITCHAT_PROMPT
from agent_backend.agent.sub_agents import _run_agent_loop


async def chitchat_agent_node(state: MultiAgentState) -> dict:
    """Handle casual conversation. No tools, one response only."""
    return await _run_agent_loop(
        state,
        agent_type="chitchat",
        tools=[],
        system_prompt=CHITCHAT_PROMPT,
        max_iterations=1,
        fast=True,
    )
