from agent_backend.utils.redis_client import get_redis


def _summary_key(user_id: str, session_id: str) -> str:
    return f"agent:summary:{user_id}:{session_id}"


async def get_summary(user_id: str, session_id: str) -> str:
    redis = await get_redis()
    val = await redis.get(_summary_key(user_id, session_id))
    return val or ""


async def set_summary(user_id: str, session_id: str, summary: str):
    redis = await get_redis()
    await redis.set(_summary_key(user_id, session_id), summary)


async def delete_summary(user_id: str, session_id: str):
    redis = await get_redis()
    await redis.delete(_summary_key(user_id, session_id))
