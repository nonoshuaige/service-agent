"""Sub-agent implementations — chitchat, pre_sales, after_sales."""

import logging
from langchain_core.messages import SystemMessage, ToolMessage

from agent_backend.agent.nodes import create_llm
from agent_backend.agent.handoff import is_handoff_tool, extract_handoff_target

logger = logging.getLogger(__name__)


async def _run_agent_loop(
    state: dict,
    agent_type: str,
    tools: list,
    system_prompt: str,
    max_iterations: int = 5,
) -> dict:
    """Shared tool-calling loop for sub-agents.

    1. Build LLM input with agent-specific system prompt
    2. LLM call → if tool_calls: execute (or handoff) → loop back
    3. Return accumulated messages + handoff flags

    Returns:
        dict with keys: messages, handoff_to, handoff_reason,
                        handoff_from, current_agent
    """
    llm = create_llm()
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    # Build LLM input (system prompt is NOT persisted to state messages)
    llm_messages = [SystemMessage(content=system_prompt)]

    # Inject handoff context if arriving from another agent
    hf_to = state.get("handoff_to", "")
    if hf_to == agent_type:
        llm_messages.append(SystemMessage(
            content=f"[Handoff from {state.get('handoff_from', '?')}] "
                    f"{state.get('handoff_reason', '')}\n"
                    f"请优先处理与你职责相关的部分，完成后再考虑是否需要转接。"
        ))

    # Add conversation history
    llm_messages.extend(list(state.get("messages", [])))

    new_messages = []
    handoff_to = ""
    handoff_reason = ""

    for _ in range(max_iterations):
        response = await llm_with_tools.ainvoke(llm_messages)
        new_messages.append(response)
        llm_messages.append(response)

        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            break  # Agent finished — no more tool calls

        for tc in tool_calls:
            tool_name = tc.get("name", "unknown")
            tool_args = tc.get("args", {})
            tool_call_id = tc.get("id", "")

            # ── Handoff tools: set state flags, break loop ──
            if is_handoff_tool(tool_name):
                # Prevent infinite handoff loops: max 1 handoff per turn.
                handoff_count = state.get("handoff_count", 0)
                if handoff_count >= 1:
                    logger.warning(
                        f"Handoff suppressed (count={handoff_count}): "
                        f"agent={agent_type} attempted handoff to {extract_handoff_target(tool_name)}"
                    )
                    new_messages.append(ToolMessage(
                        content="[Handoff suppressed] 已达到最大转接次数。"
                                "请基于当前已有的信息直接回复用户。",
                        tool_call_id=tool_call_id,
                    ))
                    llm_messages.append(new_messages[-1])
                    continue  # Don't break — let agent respond directly

                handoff_to = extract_handoff_target(tool_name)
                handoff_reason = tool_args.get("reason", "")
                new_messages.append(ToolMessage(
                    content=f"[Handoff → {handoff_to}] {handoff_reason}",
                    tool_call_id=tool_call_id,
                ))
                break  # Exit inner tool loop

            # ── Regular tools: execute ──
            tool_func = next((t for t in tools if t.name == tool_name), None)
            try:
                if tool_func:
                    result = await tool_func.ainvoke(tool_args)
                    result_str = str(result)
                else:
                    result_str = f"Tool '{tool_name}' not found"
            except Exception as e:
                logger.error(f"Tool {tool_name} error: {e}")
                result_str = f"Tool execution error: {str(e)}"

            tool_msg = ToolMessage(content=result_str, tool_call_id=tool_call_id)
            new_messages.append(tool_msg)
            llm_messages.append(tool_msg)

        if handoff_to:
            break  # Exit outer iteration loop on handoff

    return {
        "messages": new_messages,
        "handoff_to": handoff_to,
        "handoff_reason": handoff_reason,
        "handoff_from": agent_type if handoff_to else "",
        "current_agent": agent_type,
        "step_count": state.get("step_count", 0) + 1,
        "handoff_count": state.get("handoff_count", 0) + (1 if handoff_to else 0),
    }
