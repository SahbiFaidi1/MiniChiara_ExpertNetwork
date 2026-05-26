from __future__ import annotations

import logging
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    port: int = Field(default=8000, validation_alias="PORT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    public_base_url: str = Field(default="http://localhost:8000", validation_alias="PUBLIC_BASE_URL")

    # Slack
    # Optional so you can run CLI/import without Slack configured.
    slack_bot_token: str = Field(default="", validation_alias="SLACK_BOT_TOKEN")
    slack_signing_secret: str = Field(default="", validation_alias="SLACK_SIGNING_SECRET")
    # Socket Mode (no ngrok): enable in Slack app + app-level token with connections:write
    slack_app_token: str = Field(default="", validation_alias="SLACK_APP_TOKEN")

    # DB
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    use_pgvector: bool = Field(default=True, validation_alias="USE_PGVECTOR")
    retrieval_top_k: int = Field(default=10, validation_alias="RETRIEVAL_TOP_K")

    # OpenAI
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_embedding_model: str = Field(default="text-embedding-3-small", validation_alias="OPENAI_EMBEDDING_MODEL")
    openai_ranking_model: str = Field(default="gpt-4.1-mini", validation_alias="OPENAI_RANKING_MODEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    return settings

