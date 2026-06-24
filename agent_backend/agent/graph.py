from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from agent_backend.agent.state import AgentState
from agent_backend.agent.nodes import agent_node
from agent_backend.agent.router import should_continue


def build_agent_graph(tools: list):
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    if tools:
        workflow.add_node("tools", ToolNode(tools))

    workflow.set_entry_point("agent")

    if tools:
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {"continue": "tools", "end": END},
        )
        workflow.add_edge("tools", "agent")
    else:
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {"continue": END, "end": END},
        )

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
