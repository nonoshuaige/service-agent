import json
import logging
from agent_backend.utils.redis_client import get_redis
from agent_backend.context.recent_chat import get_recent, append_recent
from agent_backend.storage.db import (
    get_latest_compression,
    get_recent_messages,
    get_messages_before,
    get_message_count,
)

DEFAULT_RECENT_LIMIT = 20

logger = logging.getLogger(__name__)

REDIS_TTL = 7 * 24 * 3600
MAX_SESSIONS = 10


async def _refresh_ttl(key: str):
    redis = await get_redis()
    await redis.expire(key, REDIS_TTL)


async def load_context(user_id: str, session_id: str) -> dict:
    """Load context for prompt building: compression summary + recent messages.

    Returns:
        {"compression": str | None, "recent": list[dict], "recent_seq_start": int}
    """
    compression = await get_latest_compression(session_id)
    recent = await get_recent(user_id, session_id)

    # Determine where the recent messages start (for building full context)
    recent_seq_start = compression["end_seq"] + 1 if compression else 0

    return {
        "compression": compression["summary"] if compression else "",
        "recent": recent,
        "recent_seq_start": recent_seq_start,
    }


async def save_turn(user_id: str, session_id: str, user_msg: str, assistant_msg: str):
    """Save a conversation turn to both DB (via append_recent) and Redis recent."""
    await append_recent(user_id, session_id, "user", user_msg)
    await append_recent(user_id, session_id, "assistant", assistant_msg)


# ── Session CRUD ───────────────────────────────────────────

def _sessions_key(user_id: str) -> str:
    return f"agent:sessions:{user_id}"


def _session_meta_key(session_id: str) -> str:
    return f"agent:session:{session_id}"


async def create_session_meta(user_id: str, session_id: str,
                               agent_type: str, title: str = "") -> str:
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
        pipe.expire(_session_meta_key(session_id), REDIS_TTL)
        pipe.zadd(_sessions_key(user_id), {session_id: ts})
        # Keep only latest MAX_SESSIONS
        pipe.zremrangebyrank(_sessions_key(user_id), 0, -(MAX_SESSIONS + 1))
        pipe.expire(_sessions_key(user_id), REDIS_TTL)
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
    await _refresh_ttl(_session_meta_key(session_id))


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
    redis = await get_redis()
    await redis.hset(_session_meta_key(session_id), "title", title)
    await _refresh_ttl(_session_meta_key(session_id))


# ── Active session tracking ─────────────────────────────────

def _active_session_key(user_id: str) -> str:
    return f"agent:active_session:{user_id}"


async def get_active_session(user_id: str) -> str | None:
    redis = await get_redis()
    sid = await redis.get(_active_session_key(user_id))
    return sid or None


async def set_active_session(user_id: str, session_id: str):
    redis = await get_redis()
    key = _active_session_key(user_id)
    await redis.set(key, session_id)
    await redis.expire(key, REDIS_TTL)


async def load_session_messages(session_id: str, limit: int = DEFAULT_RECENT_LIMIT,
                                user_id: str = "") -> dict:
    """Load recent messages for initial display, with pagination info.

    Falls back to Redis hot data when MySQL is empty for this session.

    Returns:
        {messages: list, total: int, oldest_seq: int, has_more: bool}
    """
    total = await get_message_count(session_id)
    messages = await get_recent_messages(session_id, limit)

    if total == 0 and user_id:
        # MySQL empty — try recovering from Redis hot data
        from agent_backend.storage.db import save_message as _save_msg
        redis_msgs = await get_recent(user_id, session_id, count=50)
        recovered = 0
        for i, m in enumerate(redis_msgs):
            if m.get("role") in ("user", "assistant"):
                await _save_msg(user_id, session_id, m["role"], m["content"], i)
                recovered += 1
        if recovered:
            logger.info(f"Recovered {recovered} messages from Redis for {session_id}")
            total = await get_message_count(session_id)
            messages = await get_recent_messages(session_id, limit)

    oldest_seq = messages[0]["sequence_num"] if messages else 0
    return {
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "total": total,
        "oldest_seq": oldest_seq,
        "has_more": oldest_seq > 0,
    }


async def load_messages_before(session_id: str, before_seq: int, limit: int = 20) -> dict:
    """Load older messages before a given sequence number.

    Returns:
        {messages: list, oldest_seq: int, has_more: bool}
    """
    messages = await get_messages_before(session_id, before_seq, limit)
    oldest_seq = messages[0]["sequence_num"] if messages else before_seq
    return {
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "oldest_seq": oldest_seq,
        "has_more": oldest_seq > 0,
    }
