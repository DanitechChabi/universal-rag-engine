"""Modèles configurés par chaque organisation (docs/AI_MODELS.md §2, tables ai_providers et ai_models).

Les clés d'API sont stockées chiffrées (table ``secrets``, ADR-0012) et ne sont déchiffrées qu'en
mémoire, au moment de construire l'adaptateur ; elles ne sont jamais renvoyées par l'API.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable

from sqlalchemy import Connection, text

from . import (
    AnthropicAdapter,
    GeminiAdapter,
    ModelRouter,
    ModelSpec,
    OllamaAdapter,
    OpenAICompatibleAdapter,
    ProviderAdapter,
)

DEFAULT_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "gemini": GeminiAdapter.BASE_URL,
    "anthropic": AnthropicAdapter.BASE_URL,
}


def provider_secret_purpose(provider_id: uuid.UUID | str) -> str:
    return f"provider:{provider_id}"


def read_secret(conn: Connection, box, org_id: uuid.UUID, secret_id, purpose: str) -> str | None:
    if secret_id is None or box is None:
        return None
    row = conn.execute(text("SELECT nonce, ciphertext FROM secrets WHERE id = :i"), {"i": secret_id}).first()
    return box.decrypt(org_id, purpose, row.nonce, row.ciphertext).decode() if row else None


def build_adapter(kind: str, endpoint: str | None, api_key: str | None) -> ProviderAdapter:
    if kind == "ollama":
        if not endpoint:
            raise ValueError("adresse du serveur Ollama requise")
        return OllamaAdapter(endpoint)
    if kind == "gemini":
        return GeminiAdapter(api_key or "", endpoint or DEFAULT_ENDPOINTS["gemini"])
    if kind == "anthropic":
        return AnthropicAdapter(api_key, endpoint or DEFAULT_ENDPOINTS["anthropic"])
    if kind in ("openai", "openai_compatible"):
        base = endpoint or DEFAULT_ENDPOINTS.get(kind)
        if not base:
            raise ValueError("adresse de l'API requise")
        return OpenAICompatibleAdapter(base, api_key)
    raise ValueError(f"fournisseur non pris en charge : {kind}")


def load_router(conn: Connection, org_id: uuid.UUID, box) -> ModelRouter | None:
    """Routeur des modèles de conversation activés (fournisseur activé, modèle activé et disponible).

    ``None`` si l'organisation n'a configuré aucun modèle : le routeur par défaut de l'installation
    (modèle local) s'applique alors.
    """
    rows = conn.execute(
        text("""
        SELECT m.id, m.name, m.temperature, m.max_output_tokens, m.context_window, m.timeout_s,
               m.max_concurrency, m.priority, m.input_cost_per_mtok, m.output_cost_per_mtok,
               p.id AS provider_id, p.kind::text AS kind, p.endpoint, p.locality::text AS locality, p.secret_id
        FROM ai_models m JOIN ai_providers p ON p.id = m.provider_id
        WHERE m.purpose = 'chat' AND m.enabled AND m.available AND p.enabled
        ORDER BY m.priority, m.name""")
    ).all()
    if not rows:
        return None
    adapters: dict[str, ProviderAdapter] = {}
    models: list[ModelSpec] = []
    for r in rows:
        key = str(r.provider_id)
        if key not in adapters:
            secret = read_secret(conn, box, org_id, r.secret_id, provider_secret_purpose(r.provider_id))
            try:
                adapters[key] = build_adapter(r.kind, r.endpoint, secret)
            except ValueError:
                continue  # fournisseur mal configuré : ignoré (le test de disponibilité le signale)
        models.append(
            ModelSpec(
                id=str(r.id),
                name=r.name,
                provider=key,
                locality=r.locality,
                temperature=r.temperature if r.temperature is not None else 0.1,
                max_output_tokens=r.max_output_tokens or 800,
                context_window=r.context_window or 8192,
                timeout_s=float(r.timeout_s),
                max_concurrency=r.max_concurrency,
                priority=r.priority,
                db_id=str(r.id),
                input_cost_per_mtok=float(r.input_cost_per_mtok) if r.input_cost_per_mtok is not None else None,
                output_cost_per_mtok=float(r.output_cost_per_mtok) if r.output_cost_per_mtok is not None else None,
            )
        )
    return ModelRouter(adapters, models) if models else None


class RouterCache:
    """Un routeur par organisation, reconstruit après une modification ou au plus tard après ``ttl_s``
    (plusieurs processus : la modification faite dans l'un est vue par les autres sous ``ttl_s``)."""

    def __init__(self, factory: Callable[[uuid.UUID], ModelRouter | None], ttl_s: float = 30.0) -> None:
        self._factory = factory
        self._ttl = ttl_s
        self._lock = threading.Lock()
        self._cache: dict[uuid.UUID, tuple[float, ModelRouter | None]] = {}

    def get(self, org_id: uuid.UUID) -> ModelRouter | None:
        with self._lock:
            hit = self._cache.get(org_id)
            if hit and time.monotonic() - hit[0] < self._ttl:
                return hit[1]
        router = self._factory(org_id)
        with self._lock:
            self._cache[org_id] = (time.monotonic(), router)
        return router

    def invalidate(self, org_id: uuid.UUID) -> None:
        with self._lock:
            self._cache.pop(org_id, None)
