import aiomysql
import logging
from agent_backend.config import settings

logger = logging.getLogger(__name__)

_pool: aiomysql.Pool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    sequence_num INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_msg_session (session_id, sequence_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_compressions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    start_seq INT NOT NULL,
    end_seq INT NOT NULL,
    summary TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_comp_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


async def init_db() -> aiomysql.Pool:
    global _pool
    _pool = await aiomysql.create_pool(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        db=settings.mysql_database,
        autocommit=True,
        minsize=2,
        maxsize=10,
        charset="utf8mb4",
    )
    async with _pool.acquire() as conn:
        async with conn.cursor() as cur:
            for stmt in SCHEMA.split(";"):
                stmt = stmt.strip()
                if stmt:
                    await cur.execute(stmt)
    logger.info(f"MySQL initialized at {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    return _pool


async def get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        await init_db()
    return _pool


async def close_db():
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


async def save_message(user_id: str, session_id: str, role: str,
                       content: str, sequence_num: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO agent_messages (user_id, session_id, role, content, sequence_num) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, session_id, role, content, sequence_num),
            )


async def save_messages_batch(rows: list[tuple[str, str, str, str, int]]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO agent_messages (user_id, session_id, role, content, sequence_num) "
                "VALUES (%s, %s, %s, %s, %s)",
                rows,
            )


async def get_messages(session_id: str, start_seq: int = 0, limit: int = 100) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT role, content, sequence_num, created_at "
                "FROM agent_messages "
                "WHERE session_id = %s AND sequence_num >= %s "
                "ORDER BY sequence_num ASC LIMIT %s",
                (session_id, start_seq, limit),
            )
            return await cur.fetchall()


async def get_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT role, content, sequence_num, created_at "
                "FROM agent_messages "
                "WHERE session_id = %s "
                "ORDER BY sequence_num DESC LIMIT %s",
                (session_id, limit),
            )
            rows = list(await cur.fetchall())
            rows.reverse()
            return rows


async def get_messages_before(session_id: str, before_seq: int, limit: int = 20) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT role, content, sequence_num, created_at "
                "FROM agent_messages "
                "WHERE session_id = %s AND sequence_num < %s "
                "ORDER BY sequence_num DESC LIMIT %s",
                (session_id, before_seq, limit),
            )
            rows = list(await cur.fetchall())
            rows.reverse()
            return rows


async def get_message_count(session_id: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT COUNT(*) as cnt FROM agent_messages WHERE session_id = %s",
                (session_id,),
            )
            row = await cur.fetchone()
            return row["cnt"] if row else 0


async def save_compression(user_id: str, session_id: str,
                           start_seq: int, end_seq: int, summary: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO agent_compressions (user_id, session_id, start_seq, end_seq, summary) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, session_id, start_seq, end_seq, summary),
            )


async def get_latest_compression(session_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT start_seq, end_seq, summary, created_at "
                "FROM agent_compressions "
                "WHERE session_id = %s "
                "ORDER BY end_seq DESC LIMIT 1",
                (session_id,),
            )
            return await cur.fetchone()


async def get_compressions(session_id: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT start_seq, end_seq, summary, created_at "
                "FROM agent_compressions "
                "WHERE session_id = %s "
                "ORDER BY end_seq ASC",
                (session_id,),
            )
            return await cur.fetchall()
