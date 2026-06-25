import aiosqlite
import logging
from agent_backend.config import settings

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_msg_session
    ON agent_messages(session_id, sequence_num);

CREATE TABLE IF NOT EXISTS agent_compressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    start_seq INTEGER NOT NULL,
    end_seq INTEGER NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_comp_session
    ON agent_compressions(session_id);
"""


async def init_db() -> aiosqlite.Connection:
    global _db
    db_path = settings.db_path
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()
    logger.info(f"SQLite initialized at {db_path}")
    return _db


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        await init_db()
    return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def save_message(user_id: str, session_id: str, role: str,
                       content: str, sequence_num: int):
    db = await get_db()
    await db.execute(
        "INSERT INTO agent_messages (user_id, session_id, role, content, sequence_num) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, role, content, sequence_num),
    )
    await db.commit()


async def save_messages_batch(rows: list[tuple[str, str, str, str, int]]):
    """rows: [(user_id, session_id, role, content, seq), ...]"""
    db = await get_db()
    await db.executemany(
        "INSERT INTO agent_messages (user_id, session_id, role, content, sequence_num) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    await db.commit()


async def get_messages(session_id: str, start_seq: int = 0, limit: int = 100) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT role, content, sequence_num, created_at "
        "FROM agent_messages "
        "WHERE session_id = ? AND sequence_num >= ? "
        "ORDER BY sequence_num ASC LIMIT ?",
        (session_id, start_seq, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    """Get the last N messages (newest first in query, returned in chronological order)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT role, content, sequence_num, created_at "
        "FROM agent_messages "
        "WHERE session_id = ? "
        "ORDER BY sequence_num DESC LIMIT ?",
        (session_id, limit),
    )
    rows = await cursor.fetchall()
    results = [dict(r) for r in rows]
    results.reverse()  # chronological order
    return results


async def get_messages_before(session_id: str, before_seq: int, limit: int = 20) -> list[dict]:
    """Get messages with sequence_num < before_seq, newest-first, then reversed to chronological."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT role, content, sequence_num, created_at "
        "FROM agent_messages "
        "WHERE session_id = ? AND sequence_num < ? "
        "ORDER BY sequence_num DESC LIMIT ?",
        (session_id, before_seq, limit),
    )
    rows = await cursor.fetchall()
    results = [dict(r) for r in rows]
    results.reverse()
    return results


async def get_message_count(session_id: str) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM agent_messages WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


async def save_compression(user_id: str, session_id: str,
                           start_seq: int, end_seq: int, summary: str):
    db = await get_db()
    await db.execute(
        "INSERT INTO agent_compressions (user_id, session_id, start_seq, end_seq, summary) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, start_seq, end_seq, summary),
    )
    await db.commit()


async def get_latest_compression(session_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT start_seq, end_seq, summary, created_at "
        "FROM agent_compressions "
        "WHERE session_id = ? "
        "ORDER BY end_seq DESC LIMIT 1",
        (session_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_compressions(session_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT start_seq, end_seq, summary, created_at "
        "FROM agent_compressions "
        "WHERE session_id = ? "
        "ORDER BY end_seq ASC",
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
