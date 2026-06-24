import json
from agent_backend.utils.redis_client import get_redis

MAX_RECENT = 50
PROMPT_WINDOW = 10


def _recent_key(user_id: str, session_id: str) -> str:
    return f"agent:recent:{user_id}:{session_id}"


async def append_recent(user_id: str, session_id: str, role: str, content: str):
    redis = await get_redis()
    entry = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    key = _recent_key(user_id, session_id)
    async with redis.pipeline() as pipe:
        pipe.lpush(key, entry)
        pipe.ltrim(key, 0, MAX_RECENT - 1)
        await pipe.execute()


async def get_recent(user_id: str, session_id: str, count: int = PROMPT_WINDOW) -> list[dict]:
    redis = await get_redis()
    items = await redis.lrange(_recent_key(user_id, session_id), 0, count - 1)
    messages = []
    for item in reversed(items):
        try:
            messages.append(json.loads(item))
        except json.JSONDecodeError:
            pass
    return messages


async def clear_recent(user_id: str, session_id: str):
    redis = await get_redis()
    await redis.delete(_recent_key(user_id, session_id))
