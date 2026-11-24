"""Configuration externalisée (variables d'environnement préfixées URAG_)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="URAG_", env_file=".env", extra="ignore")

    mode: str = "server"
    env: str = "development"

    database_url: str = "postgresql+psycopg://urag_app@localhost:5432/urag"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None

    ollama_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    embedding_dimension: int = 1024
    chat_model: str = "qwen2.5:1.5b"

    master_key_file: Path | None = None
    # Clé de signature des jetons d'accès : dérivée de la clé maîtresse si absente.
    token_secret: SecretStr | None = None
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_hours: int = 12

    tmp_dir: Path = Path("/tmp/urag")  # noqa: S108 - surchargé en production

    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 150
    retrieval_candidates: int = 30
    context_passages: int = 6

    cookie_secure: bool = True
    login_max_failures: int = 5

    extra_ollama_options: dict[str, float] = Field(default_factory=dict)


@lru_cache
def get_settings() -> Settings:
    return Settings()
