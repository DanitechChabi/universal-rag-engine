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
    embedding_backend: str = "ollama"  # onnx (recommandé, ADR-0018) | ollama
    embedding_model_dir: Path | None = None  # dossier du modèle ONNX (model_int8.onnx + tokenizer.json)
    embedding_model: str = "bge-m3"
    embedding_dimension: int = 1024
    chat_model: str = "qwen2.5:1.5b"

    master_key_file: Path | None = None
    # Clé de signature des jetons d'accès : dérivée de la clé maîtresse si absente.
    token_secret: SecretStr | None = None
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_hours: int = 12

    ocr_engine: str = "tesseract"  # tesseract | rapidocr | none (ADR-0017)
    tmp_dir: Path = Path("/tmp/urag")  # noqa: S108 - surchargé en production

    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 150
    retrieval_candidates: int = 30
    late_access_check: bool = True  # droits revérifiés auprès des sources qui le permettent
    rerank_backend: str = "none"  # none | onnx (ADR-0021)
    rerank_model_dir: Path = Path.home() / "urag-models" / "bge-reranker-v2-m3-onnx"
    rerank_candidates: int = 10  # même qualité que 20, deux fois plus rapide (ADR-0021, mesure phase 7)
    search_concurrency: int = 4  # recherches simultanées par processus de l'API ; les autres attendent
    search_queue_timeout_s: float = 60.0  # au-delà : refus « service occupé » (503)
    tika_url: str | None = None  # ex. http://tika:9998 ; absent : formats anciens exclus
    context_passages: int = 6

    cookie_secure: bool = True
    api_host: str = "127.0.0.1"  # 0.0.0.0 dans le conteneur (réseau interne seulement)
    api_port: int = 8000
    api_workers: int = 1
    onnx_threads: int = 0  # fils de calcul ONNX par processus ; 0 : cœurs / processus de l'API (tous pour le worker)
    forwarded_allow_ips: str = "127.0.0.1"  # adresse du relais HTTPS autorisé à transmettre l'IP cliente
    login_max_failures: int = 5

    extra_ollama_options: dict[str, float] = Field(default_factory=dict)


@lru_cache
def get_settings() -> Settings:
    return Settings()
