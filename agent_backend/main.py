import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent_backend.api.agent_controller import router as agent_router
from agent_backend.utils.redis_client import get_redis, close_redis
from agent_backend.config import settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = await get_redis()
    await redis.ping()
    logging.info("Redis connected successfully")

    from agent_backend.storage.db import init_db
    await init_db()
    logging.info("MySQL initialized successfully")

    yield

    await close_redis()
    from agent_backend.storage.db import close_db
    await close_db()
    logging.info("Redis + MySQL connections closed")


app = FastAPI(title="Agent Intelligent Assistant", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent_backend.main:app", host="0.0.0.0", port=settings.agent_port, reload=True)
