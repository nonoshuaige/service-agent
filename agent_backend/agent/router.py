from agent_backend.agent.state import AgentState


def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    if not messages:
        return "end"

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"
    return "end"
