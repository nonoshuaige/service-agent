"""Multi-agent supervisor graph — LangGraph StateGraph with supervisor routing.

Builds a graph with: rewrite_intent → supervisor → chitchat|pre_sales|after_sales.
Sub-agents can handoff to each other via supervisor re-routing.
"""

from langgraph.graph import StateGraph, END

from agent_backend.agent.state import MultiAgentState
from agent_backend.agent.intents import rewrite_intent_node
from agent_backend.agent.supervisor import supervisor_node, _supervisor_dispatch
from agent_backend.agent.sub_agents.chitchat import chitchat_agent_node
from agent_backend.agent.sub_agents.pre_sales import pre_sales_agent_node
from agent_backend.agent.sub_agents.after_sales import after_sales_agent_node
from agent_backend.agent.handoff import pre_sales_router, after_sales_router


def build_multi_agent_graph() -> StateGraph:
    """Build the supervisor-based multi-agent graph.

    Node chain:
        rewrite_intent → supervisor → chitchat|pre_sales|after_sales
        pre_sales/after_sales → router → END | supervisor(handoff loop)
    """
    workflow = StateGraph(MultiAgentState)

    # ── Add nodes ──
    workflow.add_node("rewrite_intent", rewrite_intent_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("chitchat_agent", chitchat_agent_node)
    workflow.add_node("pre_sales_agent", pre_sales_agent_node)
    workflow.add_node("after_sales_agent", after_sales_agent_node)

    # ── Entry point ──
    workflow.set_entry_point("rewrite_intent")

    # ── rewrite_intent → supervisor (always) ──
    workflow.add_edge("rewrite_intent", "supervisor")

    # ── supervisor → conditional dispatch ──
    workflow.add_conditional_edges(
        "supervisor",
        _supervisor_dispatch,
        {
            "chitchat": "chitchat_agent",
            "pre_sales": "pre_sales_agent",
            "after_sales": "after_sales_agent",
            "finish": END,
        },
    )

    # ── chitchat → END (simple dead-end, no handoff needed) ──
    workflow.add_edge("chitchat_agent", END)

    # ── pre_sales → conditional (handoff / done) ──
    workflow.add_conditional_edges(
        "pre_sales_agent",
        pre_sales_router,
        {
            "supervisor": "supervisor",
            "end": END,
        },
    )

    # ── after_sales → conditional (handoff / done) ──
    workflow.add_conditional_edges(
        "after_sales_agent",
        after_sales_router,
        {
            "supervisor": "supervisor",
            "end": END,
        },
    )

    return workflow.compile()
