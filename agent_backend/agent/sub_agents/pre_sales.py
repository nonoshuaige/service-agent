"""Pre-sales agent — search events, create orders, calculator, handoff to after-sales."""

from agent_backend.agent.state import MultiAgentState
from agent_backend.agent.prompts import PRE_SALES_PROMPT
from agent_backend.agent.sub_agents import _run_agent_loop
from agent_backend.tools.registry import get_agent_tools
from agent_backend.agent.handoff import handoff_to_after_sales


async def pre_sales_agent_node(state: MultiAgentState) -> dict:
    """Pre-sales: query events, buy tickets, with handoff to after-sales."""
    tools = list(get_agent_tools("pre_sales")) + [handoff_to_after_sales]
    return await _run_agent_loop(
        state,
        agent_type="pre_sales",
        tools=tools,
        system_prompt=PRE_SALES_PROMPT,
        max_iterations=5,
    )
