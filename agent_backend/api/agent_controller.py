import json
import uuid
import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException, Body
from starlette.responses import StreamingResponse
from langchain_core.messages import AIMessage, ToolMessage

from agent_backend.api.deps import get_current_user_id
from agent_backend.models.request import CreateSessionReq, ChatStreamReq
from agent_backend.models.response import ApiResponse
from agent_backend.context.context_hub import (
    create_session_meta,
    list_sessions,
    delete_session,
    get_session_detail,
    load_context,
    save_turn,
    update_session_meta,
    rename_session,
    get_active_session,
    set_active_session,
)
from agent_backend.context.recent_chat import get_recent
from agent_backend.agent.nodes import create_llm
from agent_backend.tools.registry import get_agent_tools
from agent_backend.utils.sse import sse_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/sessions")
async def create_session(req: CreateSessionReq, user_id: str = Depends(get_current_user_id)):
    session_id = "sess_" + uuid.uuid4().hex[:12]
    await create_session_meta(user_id, session_id, req.agent_type, req.title or "")
    await set_active_session(user_id, session_id)
    detail = await get_session_detail(session_id)
    return ApiResponse.success(data=detail)


@router.get("/sessions")
async def list_user_sessions(user_id: str = Depends(get_current_user_id)):
    sessions = await list_sessions(user_id)
    active_id = await get_active_session(user_id)
    return ApiResponse.success(data={"sessions": sessions, "active_session_id": active_id})


@router.delete("/sessions/{session_id}")
async def remove_session(session_id: str, user_id: str = Depends(get_current_user_id)):
    await delete_session(user_id, session_id)
    # Clear active session pointer if the deleted session was active
    active_id = await get_active_session(user_id)
    if active_id == session_id:
        await set_active_session(user_id, "")
    return ApiResponse.success(msg="Session deleted")


@router.patch("/sessions/{session_id}")
async def rename_session_endpoint(
    session_id: str,
    body: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
):
    """Rename a session. Body: { "title": "new name" }"""
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    await rename_session(session_id, title)
    return ApiResponse.success(msg="Renamed")


@router.get("/sessions/{session_id}")
async def session_detail(session_id: str, user_id: str = Depends(get_current_user_id)):
    detail = await get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    recent = await get_recent(user_id, session_id)
    detail["messages"] = recent
    # Remember this as the active session
    await set_active_session(user_id, session_id)
    return ApiResponse.success(data=detail)


@router.post("/chat/stream")
async def chat_stream(req: ChatStreamReq, user_id: str = Depends(get_current_user_id)):
    session_id = req.session_id
    if not session_id:
        session_id = "sess_" + uuid.uuid4().hex[:12]
        await create_session_meta(user_id, session_id, req.agent_type, req.message[:20])

    await set_active_session(user_id, session_id)

    tools = get_agent_tools(req.agent_type)
    llm = create_llm()
    context = await load_context(user_id, session_id)

    async def event_generator():
        try:
            from agent_backend.agent.prompt_builder import build_system_prompt, build_messages

            tools_desc = "\n".join(f"- {t.name}: {t.description}" for t in tools) if tools else ""
            system_prompt = build_system_prompt(
                long_term=context.get("long_term", {}),
                summary=context.get("summary", ""),
                tools_desc=tools_desc,
            )
            recent_msgs = context.get("recent", [])
            messages = build_messages(system_prompt, recent_msgs, req.message)

            yield sse_event("thinking", {"step": 1, "content": "正在分析你的问题..."})

            if tools:
                llm_with_tools = llm.bind_tools(tools)
            else:
                llm_with_tools = llm

            # Use ainvoke (non-streaming) for reliable tool-call detection.
            # Streaming chunks do not reliably carry complete tool_calls across
            # all OpenAI-compatible providers (Zhipu, DeepSeek, etc.).
            response = await llm_with_tools.ainvoke(messages)

            if hasattr(response, "tool_calls") and response.tool_calls:
                # Append the full AI response (with all tool_calls) once
                messages.append(response)

                for tc in response.tool_calls:
                    tool_name = tc.get("name", "unknown")
                    tool_args = tc.get("args", {})
                    tool_call_id = tc.get("id", "")

                    yield sse_event("tool_call", {
                        "tool": tool_name,
                        "input": tool_args,
                        "status": "running",
                    })

                    try:
                        tool_func = next((t for t in tools if t.name == tool_name), None)
                        if tool_func:
                            result = await tool_func.ainvoke(tool_args)
                            result_str = str(result)
                        else:
                            result_str = f"Tool {tool_name} not found"
                    except Exception as e:
                        result_str = f"Tool execution error: {str(e)}"

                    yield sse_event("tool_result", {
                        "tool": tool_name,
                        "output": result_str,
                    })

                    messages.append(ToolMessage(content=result_str, tool_call_id=tool_call_id))

                yield sse_event("thinking", {"step": 2, "content": "正在整理结果..."})

                final_response = await llm.ainvoke(messages)
                full_response = str(final_response.content) if final_response.content else ""
                yield sse_event("final", {"content": full_response, "session_id": session_id})
            else:
                full_response = str(response.content) if response.content else ""
                yield sse_event("final", {"content": full_response, "session_id": session_id})

            await save_turn(user_id, session_id, req.message, full_response[:500])
            await update_session_meta(session_id, full_response[:100])

            yield sse_event("done", {})

        except Exception as e:
            logger.error(f"Stream error: {traceback.format_exc()}")
            yield sse_event("error", {"message": f"处理请求时出错: {str(e)}"})
            yield sse_event("done", {})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
