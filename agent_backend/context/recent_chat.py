import json
import asyncio
import logging
from agent_backend.utils.redis_client import get_redis
from agent_backend.storage.db import (
    save_message,
    save_compression,
    get_latest_compression,
)
from agent_backend.config import settings

logger = logging.getLogger(__name__)

MAX_RECENT = 30
COMPRESS_TRIGGER = 20
PROMPT_WINDOW = 10
REDIS_TTL = 7 * 24 * 3600  # 7 days


def _recent_key(user_id: str, session_id: str) -> str:
    return f"agent:recent:{user_id}:{session_id}"


async def _refresh_ttl(key: str):
    redis = await get_redis()
    await redis.expire(key, REDIS_TTL)


async def _generate_compression(user_id: str, session_id: str,
                                 entries: list[dict]) -> str:
    """Call a lightweight LLM to compress the first COMPRESS_TRIGGER entries."""
    from agent_backend.agent.nodes import create_llm

    # Build compression prompt
    lines = [
        "请将以下对话压缩为关键信息摘要（3-5句话）：",
        "",
    ]

    min_seq = None
    max_seq = None
    for e in entries:
        if e.get("type") == "compressed":
            lines.append(f"[前次摘要(seq {e['start_seq']}-{e['end_seq']})] {e['content']}")
            if min_seq is None or e["start_seq"] < min_seq:
                min_seq = e["start_seq"]
            if max_seq is None or e["end_seq"] > max_seq:
                max_seq = e["end_seq"]
        else:
            seq = e.get("seq", 0)
            lines.append(f"[seq {seq}] {e['role']}: {e['content']}")
            if min_seq is None or seq < min_seq:
                min_seq = seq
            if max_seq is None or seq > max_seq:
                max_seq = seq

    lines.append("")
    lines.append("要求：保留用户的核心需求、已获得的关键信息、未解决的问题。")

    prompt = "\n".join(lines)

    try:
        llm = create_llm()  # Use the summary model? We use the main LLM for now
        from langchain_core.messages import HumanMessage
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        summary = str(response.content) if response.content else ""
        # Save to DB
        await save_compression(user_id, session_id,
                               start_seq=min_seq or 0,
                               end_seq=max_seq or 0,
                               summary=summary)
        logger.info(f"Compression saved for {session_id}: seq {min_seq}-{max_seq}")
        return summary, min_seq or 0, max_seq or 0
    except Exception as e:
        logger.error(f"Compression failed for {session_id}: {e}")
        return None, None, None


async def append_recent(user_id: str, session_id: str, role: str, content: str):
    """Append a message to the recent list, trigger compression if >= 20."""
    redis = await get_redis()
    key = _recent_key(user_id, session_id)

    # Get current message count from DB for sequence numbering
    from agent_backend.storage.db import get_message_count
    seq = await get_message_count(session_id)

    # Save to DB (full history)
    await save_message(user_id, session_id, role, content, seq)

    # Push to Redis recent list
    entry = json.dumps({
        "type": "message",
        "role": role,
        "content": content,
        "seq": seq,
    }, ensure_ascii=False)
    await redis.lpush(key, entry)
    await redis.ltrim(key, 0, MAX_RECENT - 1)
    await _refresh_ttl(key)

    # Check if compression needed
    length = await redis.llen(key)
    if length >= COMPRESS_TRIGGER:
        asyncio.create_task(_compress_and_replace(user_id, session_id))


async def _compress_and_replace(user_id: str, session_id: str):
    """Async task: compress first 20 entries into 1 and replace in list."""
    redis = await get_redis()
    key = _recent_key(user_id, session_id)

    # Get all entries (oldest first)
    all_entries_raw = await redis.lrange(key, 0, -1)
    # Redis list is newest-first; reverse for chronological order
    all_entries = []
    for raw in reversed(all_entries_raw):
        try:
            all_entries.append(json.loads(raw))
        except json.JSONDecodeError:
            pass

    if len(all_entries) < COMPRESS_TRIGGER:
        return

    # Take first 20 for compression (oldest)
    to_compress = all_entries[:COMPRESS_TRIGGER]
    remaining = all_entries[COMPRESS_TRIGGER:]

    summary, start_seq, end_seq = await _generate_compression(
        user_id, session_id, to_compress)

    if summary is None:
        return  # compression failed, skip

    # Build new list: [compressed_entry] + remaining, newest first
    compressed_entry = json.dumps({
        "type": "compressed",
        "start_seq": start_seq,
        "end_seq": end_seq,
        "content": summary,
    }, ensure_ascii=False)

    # Rebuild: remaining (oldest first) + compressed, then reverse to newest-first
    new_entries = [compressed_entry]  # compressed goes first (will be oldest)
    for entry in remaining:
        new_entries.append(json.dumps(entry, ensure_ascii=False))

    # Delete and rebuild the key
    async with redis.pipeline() as pipe:
        pipe.delete(key)
        if new_entries:
            # Reverse so newest is at head
            for e in reversed(new_entries):
                pipe.lpush(key, e)
        pipe.expire(key, REDIS_TTL)
        await pipe.execute()

    logger.info(f"Compression applied for {session_id}: "
                f"seq {start_seq}-{end_seq}, recent size now {len(new_entries)}")


async def get_recent(user_id: str, session_id: str,
                     count: int = PROMPT_WINDOW) -> list[dict]:
    """Load recent entries from Redis. Returns newest `count` messages."""
    redis = await get_redis()
    items = await redis.lrange(_recent_key(user_id, session_id), 0, count - 1)
    messages = []
    for item in reversed(items):  # oldest first
        try:
            entry = json.loads(item)
            if entry.get("type") == "compressed":
                # Still include it, caller can decide how to use
                messages.append({"role": "system", "content": f"[对话摘要] {entry['content']}"})
            else:
                messages.append({"role": entry["role"], "content": entry["content"]})
        except json.JSONDecodeError:
            pass
    return messages


async def clear_recent(user_id: str, session_id: str):
    redis = await get_redis()
    await redis.delete(_recent_key(user_id, session_id))


async def get_messages_since(session_id: str, since_seq: int = 0) -> list[dict]:
    """Load full message history from DB since a given sequence number."""
    from agent_backend.storage.db import get_messages
    return await get_messages(session_id, since_seq)
