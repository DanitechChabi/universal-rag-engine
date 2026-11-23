"""Model Router (ADR-0014, docs/AI_MODELS.md §2).

Phase 1 : adaptateur Ollama (local) et application de la politique de
confidentialité. Les adaptateurs externes (Claude, Gemini, OpenAI) arrivent en
phase 5 ; la règle « jamais de bascule vers l'externe si interdite » est déjà
appliquée et testée.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol

import httpx

Locality = Literal["local", "external"]


class DataKind(Enum):
    QUESTION = "question"
    DOCUMENTS = "documents"
    HISTORY = "history"


@dataclass(frozen=True)
class Policy:
    mode: Literal["local_only", "hybrid", "cloud_allowed"] = "local_only"
    allow_external_questions: bool = False
    allow_external_documents: bool = False
    allow_fallback_to_external: bool = False
    notify_user_on_external: bool = True

    def allows_external(self, kinds: set[DataKind]) -> bool:
        if self.mode == "local_only":
            return False
        if DataKind.DOCUMENTS in kinds and not self.allow_external_documents:
            return False
        if (DataKind.QUESTION in kinds or DataKind.HISTORY in kinds) and not (
            self.allow_external_questions or self.mode == "cloud_allowed"
        ):
            return False
        return True


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    provider: str
    locality: Locality
    temperature: float = 0.1
    max_output_tokens: int = 800
    context_window: int = 8192
    timeout_s: float = 300.0
    max_concurrency: int = 2
    priority: int = 100


@dataclass
class ChatResult:
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model: ModelSpec | None = None


class PolicyError(Exception):
    """L'appel violerait la politique de confidentialité de l'organisation."""


class ProviderError(Exception):
    pass


class ProviderAdapter(Protocol):
    def health(self) -> bool: ...
    def chat(self, model: ModelSpec, messages: list[ChatMessage], result: ChatResult) -> Iterator[str]: ...


class OllamaAdapter:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def health(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/api/version", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    def available_models(self) -> set[str]:
        r = httpx.get(f"{self.base_url}/api/tags", timeout=10)
        r.raise_for_status()
        return {m["name"] for m in r.json().get("models", [])}

    def chat(self, model: ModelSpec, messages: list[ChatMessage], result: ChatResult) -> Iterator[str]:
        body = {
            "model": model.name, "stream": True,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": model.temperature, "num_predict": model.max_output_tokens,
                        "num_ctx": model.context_window},
        }
        try:
            with httpx.stream("POST", f"{self.base_url}/api/chat", json=body, timeout=model.timeout_s) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise ProviderError(chunk["error"])
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        result.tokens_in = chunk.get("prompt_eval_count", 0)
                        result.tokens_out = chunk.get("eval_count", 0)
        except httpx.HTTPError as e:
            raise ProviderError(f"Ollama : {e}") from e


@dataclass
class ModelRouter:
    adapters: dict[str, ProviderAdapter]
    models: list[ModelSpec]
    _semaphores: dict[str, threading.BoundedSemaphore] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for m in self.models:
            self._semaphores[m.id] = threading.BoundedSemaphore(m.max_concurrency)

    def candidates(self, policy: Policy, kinds: set[DataKind], requested: str | None = None) -> list[ModelSpec]:
        allowed = [m for m in self.models if m.locality == "local" or policy.allows_external(kinds)]
        allowed.sort(key=lambda m: (m.id != requested, m.priority))
        return allowed

    def chat(self, policy: Policy, kinds: set[DataKind], messages: list[ChatMessage],
             requested: str | None = None, queue_timeout_s: float = 120.0) -> tuple[ChatResult, Iterator[str]]:
        """Choisit le modèle autorisé et renvoie (résultat, flux de texte).

        Si le modèle préféré échoue avant d'avoir produit du texte, le suivant est
        essayé **uniquement** s'il est autorisé par la politique ; un modèle externe
        n'est jamais utilisé en secours si ``allow_fallback_to_external`` est faux.
        """
        models = self.candidates(policy, kinds, requested)
        if not models:
            raise PolicyError("aucun modèle autorisé par la politique de l'organisation")
        first_locality = models[0].locality
        if first_locality == "local" and not policy.allow_fallback_to_external:
            models = [m for m in models if m.locality == "local"]
        result = ChatResult()

        def stream() -> Iterator[str]:
            errors = []
            for model in models:
                sem = self._semaphores[model.id]
                if not sem.acquire(timeout=queue_timeout_s):
                    errors.append(f"{model.name} : file d'attente pleine")
                    continue
                started = time.monotonic()
                produced = False
                try:
                    result.model = model
                    for piece in self.adapters[model.provider].chat(model, messages, result):
                        produced = True
                        yield piece
                    result.latency_ms = int((time.monotonic() - started) * 1000)
                    return
                except ProviderError as e:
                    if produced:
                        raise
                    errors.append(f"{model.name} : {e}")
                finally:
                    sem.release()
            raise ProviderError("; ".join(errors) or "aucun modèle disponible")

        return result, stream()
