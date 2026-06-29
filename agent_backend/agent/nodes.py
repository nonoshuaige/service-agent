"""LLM factory — creates ChatOpenAI instances for Zhipu / DeepSeek.

The old agent_node is DEPRECATED since v1.5 (supervisor-based multi-agent).
Real agent logic now lives in agent/sub_agents/ via _run_agent_loop.
"""

import logging
from langchain_openai import ChatOpenAI
from agent_backend.config import settings

logger = logging.getLogger(__name__)


def create_llm(provider: str | None = None, fast: bool = False) -> ChatOpenAI:
    """Create a ChatOpenAI instance for the configured or given provider.

    Args:
        provider: LLM provider name (zhipu/deepseek). None = use settings.
        fast: If True, use the summary model (glm-4-flash) for low-latency tasks.
    """
    provider = provider or settings.llm_provider
    model = settings.summary_model if fast else settings.zhipu_model

    if provider == "zhipu":
        return ChatOpenAI(
            model=model,
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            temperature=0.7,
            streaming=False,
            request_timeout=30,
        )
    elif provider == "deepseek":
        return ChatOpenAI(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0.7,
            streaming=False,
            request_timeout=30,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


# ── Legacy agent_node (deprecated, not used by supervisor graph) ──

async def agent_node(state: "AgentState") -> "AgentState":
    """DEPRECATED since v1.5. Kept for reference only.
    Use agent/sub_agents/* via the supervisor graph instead.
    """
    from agent_backend.agent.state import AgentState
    from agent_backend.agent.prompt_builder import build_system_prompt, build_messages
    from agent_backend.tools.registry import get_agent_tools

    llm = create_llm()
    tools = get_agent_tools(state.get("agent_type", "general"))

    tools_desc = "\n".join(f"- {t.name}: {t.description}" for t in tools) if tools else ""
    system_prompt = build_system_prompt(
        compression="",
        tools_desc=tools_desc,
    )

    all_messages = list(state["messages"])
    recent = []
    for m in all_messages[-20:]:
        if hasattr(m, "type"):
            if m.type == "human":
                recent.append({"role": "user", "content": m.content})
            elif m.type == "ai":
                recent.append({"role": "assistant", "content": m.content})

    user_query = ""
    for m in reversed(all_messages):
        if hasattr(m, "type") and m.type == "human":
            user_query = str(m.content)
            break

    messages = build_messages(system_prompt, recent[:-1] if recent else [], user_query)

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
