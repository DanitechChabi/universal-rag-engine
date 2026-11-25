"""Assemblage des services partagés par l'API (une instance par processus)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from functools import cached_property

from urag_core.ai import ModelRouter, ModelSpec, OllamaAdapter
from urag_core.config import Settings
from urag_core.embeddings import Encoder, build_encoder
from urag_core.ingestion import IngestionService
from urag_core.rag import RagOrchestrator
from urag_core.retrieval import Retriever
from urag_core.security import PasswordHasher, SecretBox, TokenService, load_master_key
from urag_core.storage import Database, VectorStore


@dataclass
class AppState:
    settings: Settings
    db: Database
    vectors: VectorStore
    tokens: TokenService
    hasher: PasswordHasher = field(default_factory=PasswordHasher)
    encoder_override: Encoder | None = None
    router_override: ModelRouter | None = None

    @cached_property
    def encoder(self) -> Encoder:
        return self.encoder_override or build_encoder(self.settings)

    @cached_property
    def ingestion(self) -> IngestionService:
        from urag_core.ocr import build_engine

        return IngestionService(
            self.db,
            self.vectors,
            self.encoder,
            self.settings.tmp_dir,
            ocr=build_engine(self.settings.ocr_engine),
            tika_url=self.settings.tika_url,
        )

    @cached_property
    def reranker(self):
        from urag_core.rerank import build_reranker

        return build_reranker(self.settings)

    @cached_property
    def retriever(self) -> Retriever:
        with self.db.anonymous() as conn:
            profile = self.ingestion.profile(conn)
        return Retriever(
            self.vectors,
            self.encoder,
            profile.collection,
            self.settings.late_access_check,
            self.reranker,
            self.settings.rerank_candidates,
        )

    @cached_property
    def router(self) -> ModelRouter:
        if self.router_override is not None:
            return self.router_override
        model = ModelSpec(id="local-default", name=self.settings.chat_model, provider="ollama", locality="local")
        return ModelRouter({"ollama": OllamaAdapter(self.settings.ollama_url)}, [model])

    @cached_property
    def rag(self) -> RagOrchestrator:
        return RagOrchestrator(
            self.db, self.retriever, self.router, self.settings.retrieval_candidates, self.settings.context_passages
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> AppState:
        if settings.master_key_file is None:
            raise RuntimeError("URAG_MASTER_KEY_FILE est obligatoire")
        box = SecretBox(load_master_key(settings.master_key_file))
        secret = (
            settings.token_secret.get_secret_value().encode()
            if settings.token_secret
            else box.derive("access-token-signing")
        )
        tokens = TokenService(
            secret,
            timedelta(minutes=settings.access_token_ttl_minutes),
            timedelta(hours=settings.refresh_token_ttl_hours),
        )
        api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
        return cls(settings, Database(settings.database_url), VectorStore(settings.qdrant_url, api_key), tokens)
