import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    zhipu_model: str = "GLM-4.6V"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1/"
    deepseek_model: str = "deepseek-chat"
    llm_provider: str = "zhipu"
    summary_model: str = "glm-4-flash"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"

    # Service
    agent_port: int = 8000

    # Database
    db_path: str = "agent.db"

    # External
    ticket_backend_url: str = "http://localhost:8080"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
