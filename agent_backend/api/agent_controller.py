import json
import uuid
import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException, Body
from starlette.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from agent_backend.api.deps import get_current_user_id
from agent_backend.models.request import CreateSessionReq, ChatStreamReq
from agent_backend.models.response import ApiResponse
from agent_backend.agent.state import MultiAgentState
from agent_backend.agent.graph import build_multi_agent_graph
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
    load_session_messages,
    load_messages_before,
)
from agent_backend.utils.sse import sse_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

# ── Graph singleton (compiled once, stateless) ───────────────

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_multi_agent_graph()
    return _graph


# ── Session CRUD (unchanged) ──────────────────────────────────

@router.post("/sessions")
async def create_session(req: CreateSessionReq, user_id: str = Depends(get_current_user_id)):
    session_id = "sess_" + uuid.uuid4().hex[:12]
    agent_type = req.agent_type or "auto"
    await create_session_meta(user_id, session_id, agent_type, req.title or "")
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
    data = await load_session_messages(session_id, user_id=user_id)
    detail.update(data)
    await set_active_session(user_id, session_id)
    return ApiResponse.success(data=detail)


@router.get("/sessions/{session_id}/messages")
async def session_messages(
    session_id: str,
    before_seq: int = 0,
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    detail = await get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    data = await load_messages_before(session_id, before_seq, limit)
    return ApiResponse.success(data=data)


# ── SSE Chat (rewired to graph) ───────────────────────────────

@router.post("/chat/stream")
async def chat_stream(req: ChatStreamReq, user_id: str = Depends(get_current_user_id)):
    session_id = req.session_id
    if not session_id:
        session_id = "sess_" + uuid.uuid4().hex[:12]
        await create_session_meta(user_id, session_id, req.agent_type or "auto", req.message[:20])

    await set_active_session(user_id, session_id)

    # Load existing context (compression + recent messages)
    context = await load_context(user_id, session_id)

    async def event_generator():
        try:
            # ── Build initial state for the graph ──
            initial_messages = []

            # Compression summary as context
            if context.get("compression"):
                initial_messages.append(HumanMessage(
                    content=f"[对话历史摘要]\n{context['compression']}"
                ))

            # Recent messages from Redis
            for m in context.get("recent", []):
                role = m.get("role", "")
                if role == "user":
                    initial_messages.append(HumanMessage(content=m["content"]))
                elif role == "assistant":
                    initial_messages.append(AIMessage(content=m["content"]))
                elif role == "system":
                    initial_messages.append(HumanMessage(content=m["content"]))

            # Current user message
            initial_messages.append(HumanMessage(content=req.message))

            initial_state: MultiAgentState = {
                "messages": initial_messages,
                "user_id": user_id,
                "session_id": session_id,
                "user_query": req.message,
                "rewritten_query": "",
                "intent": "",
                "intent_reason": "",
                "next_agent": "",
                "supervisor_reason": "",
                "handoff_to": "",
                "handoff_reason": "",
                "handoff_from": "",
                "current_agent": "",
                "step_count": 0,
                "handoff_count": 0,
                "is_final": False,
            }

            yield sse_event("thinking", {"step": "start", "content": "正在分析你的问题..."})

            graph = _get_graph()
            config = {"configurable": {"thread_id": session_id}}
            final_text = ""
            final_agent = "chitchat"

            async for chunk in graph.astream(initial_state, config, stream_mode="updates"):
                node_name = next(iter(chunk))
                update = chunk[node_name]

                if node_name == "rewrite_intent":
                    intent = update.get("intent", "unknown")
                    rewritten = update.get("rewritten_query", "")
                    yield sse_event("thinking", {
                        "step": "intent",
                        "content": f"识别意图: {intent}",
                        "intent": intent,
                        "rewritten_query": rewritten,
                    })

                elif node_name == "supervisor":
                    next_agent = update.get("next_agent", "unknown")
                    yield sse_event("thinking", {
                        "step": "route",
                        "content": f"调度到: {next_agent}",
                    })

                elif node_name in ("chitchat_agent", "pre_sales_agent", "after_sales_agent"):
                    final_agent = node_name.replace("_agent", "")
                    new_msgs = update.get("messages", [])

                    for msg in new_msgs:
                        if isinstance(msg, AIMessage):
                            tc = getattr(msg, "tool_calls", None)
                            if tc:
                                for t in tc:
                                    yield sse_event("tool_call", {
                                        "tool": t.get("name", "unknown"),
                                        "input": t.get("args", {}),
                                        "status": "running",
                                    })
                            if msg.content:
                                final_text = str(msg.content)
                        elif isinstance(msg, ToolMessage):
                            yield sse_event("tool_result", {
                                "tool": getattr(msg, "tool_call_id", ""),
                                "output": str(msg.content),
                            })

            # Emit final text
            if final_text:
                yield sse_event("final", {"content": final_text, "session_id": session_id})

            # Persist the turn
            await save_turn(user_id, session_id, req.message, final_text[:500])
            await update_session_meta(session_id, final_text[:100] or req.message[:100])
            # Update agent_type in session meta to reflect actual classification
            await _set_session_agent_type(session_id, final_agent)

            yield sse_event("done", {})

        except Exception as e:
            logger.error(f"Graph stream error: {traceback.format_exc()}")
            yield sse_event("error", {"message": f"处理请求时出错: {str(e)}"})
            yield sse_event("done", {})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _set_session_agent_type(session_id: str, agent_type: str):
    """Update the session meta to reflect the classified agent type."""
    from agent_backend.utils.redis_client import get_redis
    try:
        redis = await get_redis()
        await redis.hset(f"agent:session:{session_id}", "agent_type", agent_type)
    except Exception:
        pass
