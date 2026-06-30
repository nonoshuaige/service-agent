"""Multi-agent graph (v1.7) — 3-agent architecture with merged router.

Graph: router → pre_sales_agent | after_sales_agent | END
Sub-agents can handoff back to router for re-routing.
"""

from langgraph.graph import StateGraph, END

from agent_backend.agent.state import MultiAgentState
from agent_backend.agent.router import router_node, router_dispatch
from agent_backend.agent.sub_agents.pre_sales import pre_sales_agent_node
from agent_backend.agent.sub_agents.after_sales import after_sales_agent_node
from agent_backend.agent.handoff import pre_sales_router, after_sales_router


def build_multi_agent_graph() -> StateGraph:
    """Build the 3-agent graph.

    Nodes:
        router — rewrite + intent + chitchat reply + routing (single LLM call)
        pre_sales_agent — event search + order creation + handoff
        after_sales_agent — order query + policy FAQ + handoff

    Flow:
        router → pre_sales_agent | after_sales_agent | END
        pre_sales_agent → END | router (handoff)
        after_sales_agent → END | router (handoff)
    """
    workflow = StateGraph(MultiAgentState)

    # ── Nodes ──
    workflow.add_node("router", router_node)
    workflow.add_node("pre_sales_agent", pre_sales_agent_node)
    workflow.add_node("after_sales_agent", after_sales_agent_node)

    # ── Entry ──
    workflow.set_entry_point("router")

    # ── router → dispatch to sub-agent or end ──
    workflow.add_conditional_edges(
        "router",
        router_dispatch,
        {
            "pre_sales": "pre_sales_agent",
            "after_sales": "after_sales_agent",
            "finish": END,
        },
    )

    # ── pre_sales → END or router (handoff) ──
    workflow.add_conditional_edges(
        "pre_sales_agent",
        pre_sales_router,
        {
            "router": "router",
            "end": END,
        },
    )

    # ── after_sales → END or router (handoff) ──
    workflow.add_conditional_edges(
        "after_sales_agent",
        after_sales_router,
        {
            "router": "router",
            "end": END,
        },
    )

    return workflow.compile()
