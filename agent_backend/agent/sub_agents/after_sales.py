"""After-sales agent — query orders, policy FAQ, handoff to pre-sales."""

from agent_backend.agent.state import MultiAgentState
from agent_backend.agent.prompts import AFTER_SALES_PROMPT
from agent_backend.agent.sub_agents import _run_agent_loop
from agent_backend.tools.registry import get_agent_tools
from agent_backend.agent.handoff import handoff_to_pre_sales


async def after_sales_agent_node(state: MultiAgentState) -> dict:
    """After-sales: query orders, policy FAQ, with handoff to pre-sales."""
    tools = list(get_agent_tools("after_sales")) + [handoff_to_pre_sales]
    return await _run_agent_loop(
        state,
        agent_type="after_sales",
        tools=tools,
        system_prompt=AFTER_SALES_PROMPT,
        max_iterations=5,
    )
