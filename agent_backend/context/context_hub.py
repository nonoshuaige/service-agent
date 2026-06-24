from agent_backend.utils.redis_client import get_redis
from agent_backend.context.memory import get_long_term
from agent_backend.context.summary import get_summary
from agent_backend.context.recent_chat import get_recent, append_recent


async def load_context(user_id: str, session_id: str) -> dict:
    long_term, summary, recent = await get_long_term(user_id), await get_summary(user_id, session_id), await get_recent(user_id, session_id)
    return {"long_term": long_term, "summary": summary, "recent": recent}


async def save_turn(user_id: str, session_id: str, user_msg: str, assistant_msg: str):
    await append_recent(user_id, session_id, "user", user_msg)
    await append_recent(user_id, session_id, "assistant", assistant_msg)


def _sessions_key(user_id: str) -> str:
    return f"agent:sessions:{user_id}"


def _session_meta_key(session_id: str) -> str:
    return f"agent:session:{session_id}"


async def create_session_meta(user_id: str, session_id: str, agent_type: str, title: str = "") -> str:
    import time
    redis = await get_redis()
    now = str(time.time())
    ts = int(time.time())
    meta = {
        "session_id": session_id,
        "title": title or "新对话",
        "agent_type": agent_type,
        "last_message": "",
        "created_at": now,
        "updated_at": now,
    }
    async with redis.pipeline() as pipe:
        pipe.hset(_session_meta_key(session_id), mapping=meta)
        pipe.zadd(_sessions_key(user_id), {session_id: ts})
        await pipe.execute()
    return session_id


async def update_session_meta(session_id: str, last_message: str):
    import time
    redis = await get_redis()
    now = str(time.time())
    await redis.hset(_session_meta_key(session_id), mapping={
        "last_message": last_message[:100],
        "updated_at": now,
    })


async def list_sessions(user_id: str) -> list[dict]:
    redis = await get_redis()
    session_ids = await redis.zrevrange(_sessions_key(user_id), 0, -1)
    sessions = []
    for sid in session_ids:
        meta = await redis.hgetall(_session_meta_key(sid))
        if meta:
            sessions.append({
                "session_id": meta.get("session_id", sid),
                "title": meta.get("title", ""),
                "agent_type": meta.get("agent_type", "general"),
                "last_message": meta.get("last_message", ""),
                "updated_at": meta.get("updated_at", ""),
                "created_at": meta.get("created_at", ""),
            })
    return sessions


async def delete_session(user_id: str, session_id: str):
    redis = await get_redis()
    async with redis.pipeline() as pipe:
        pipe.delete(_session_meta_key(session_id))
        pipe.delete(f"agent:recent:{user_id}:{session_id}")
        pipe.delete(f"agent:summary:{user_id}:{session_id}")
        pipe.zrem(_sessions_key(user_id), session_id)
        await pipe.execute()


async def get_session_detail(session_id: str) -> dict | None:
    redis = await get_redis()
    meta = await redis.hgetall(_session_meta_key(session_id))
    if not meta:
        return None
    return {
        "session_id": meta.get("session_id", session_id),
        "title": meta.get("title", ""),
        "agent_type": meta.get("agent_type", "general"),
        "created_at": meta.get("created_at", ""),
    }


async def rename_session(session_id: str, title: str):
    """Rename a session's title."""
    redis = await get_redis()
    await redis.hset(_session_meta_key(session_id), "title", title)


def _active_session_key(user_id: str) -> str:
    return f"agent:active_session:{user_id}"


async def get_active_session(user_id: str) -> str | None:
    """Get the user's last active session ID."""
    redis = await get_redis()
    sid = await redis.get(_active_session_key(user_id))
    return sid or None


async def set_active_session(user_id: str, session_id: str):
    """Remember which session the user is currently viewing."""
    redis = await get_redis()
    await redis.set(_active_session_key(user_id), session_id)
