import os
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from agent_backend.agent.state import AgentState
from agent_backend.agent.prompt_builder import build_system_prompt, build_messages
from agent_backend.tools.registry import get_agent_tools
from agent_backend.config import settings

logger = logging.getLogger(__name__)


def create_llm(provider: str | None = None) -> ChatOpenAI:
    provider = provider or settings.llm_provider

    if provider == "zhipu":
        return ChatOpenAI(
            model=settings.zhipu_model,
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            temperature=0.7,
            streaming=True,
        )
    elif provider == "deepseek":
        return ChatOpenAI(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0.7,
            streaming=True,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


async def agent_node(state: AgentState) -> AgentState:
    llm = create_llm()
    tools = get_agent_tools(state.get("agent_type", "general"))

    tools_desc = "\n".join(f"- {t.name}: {t.description}" for t in tools) if tools else ""
    system_prompt = build_system_prompt(
        long_term={},
        summary="",
        tools_desc=tools_desc,
    )

    # Reconstruct recent messages from state (exclude system messages)
    all_messages = list(state["messages"])
    recent = []
    for m in all_messages[-20:]:
        if hasattr(m, "type"):
            if m.type == "human":
                recent.append({"role": "user", "content": m.content})
            elif m.type == "ai":
                recent.append({"role": "assistant", "content": m.content})

    # Get the last user message as query
    user_query = ""
    for m in reversed(all_messages):
        if hasattr(m, "type") and m.type == "human":
            user_query = str(m.content)
            break

    messages = build_messages(system_prompt, recent[:-1] if recent else [], user_query)

    # Bind tools if available
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm

    response = await llm_with_tools.ainvoke(messages)

    new_step = state.get("step_count", 0) + 1
    has_tool_calls = bool(getattr(response, "tool_calls", None))

    return {
        "messages": [response],
        "step_count": new_step,
        "is_final": not has_tool_calls,
    }
