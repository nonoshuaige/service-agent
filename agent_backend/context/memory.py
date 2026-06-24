from agent_backend.utils.redis_client import get_redis


def _long_term_key(user_id: str) -> str:
    return f"agent:long_term:{user_id}"


async def get_long_term(user_id: str) -> dict:
    redis = await get_redis()
    return await redis.hgetall(_long_term_key(user_id))


async def set_long_term(user_id: str, data: dict):
    redis = await get_redis()
    if data:
        await redis.hset(_long_term_key(user_id), mapping=data)


async def update_long_term_field(user_id: str, field: str, value: str):
    redis = await get_redis()
    await redis.hset(_long_term_key(user_id), field, value)
