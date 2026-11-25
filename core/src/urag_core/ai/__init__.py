"""Model Router (ADR-0014, docs/AI_MODELS.md §2).

Adaptateurs : Ollama (local), Gemini (externe), compatible OpenAI (vLLM, LM Studio,
llama.cpp en local ; OpenAI en externe). La politique de confidentialité de
l'organisation est appliquée avant tout appel ; jamais de bascule vers l'externe si
elle est interdite. Les modèles de chaque organisation sont décrits en base
(``catalog.load_router``).
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
        sends_text = DataKind.QUESTION in kinds or DataKind.HISTORY in kinds
        return not sends_text or self.allow_external_questions or self.mode == "cloud_allowed"


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
    db_id: str | None = None  # identifiant dans ai_models (modèles configurés par l'organisation)
    input_cost_per_mtok: float | None = None  # prix saisi par l'administrateur (estimation)
    output_cost_per_mtok: float | None = None

    def cost(self, tokens_in: int, tokens_out: int) -> float | None:
        """Coût estimé d'un appel, si les prix ont été saisis."""
        if self.input_cost_per_mtok is None and self.output_cost_per_mtok is None:
            return None
        return (tokens_in * (self.input_cost_per_mtok or 0) + tokens_out * (self.output_cost_per_mtok or 0)) / 1e6


@dataclass
class ChatResult:
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model: ModelSpec | None = None
    finish_reason: str | None = None  # ex. STOP, MAX_TOKENS, RECITATION, SAFETY (fournisseur)

    @property
    def incomplete(self) -> bool:
        return self.finish_reason not in (None, "STOP", "stop", "end_turn")


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
            "model": model.name,
            "stream": True,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {
                "temperature": model.temperature,
                "num_predict": model.max_output_tokens,
                "num_ctx": model.context_window,
            },
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
                        result.finish_reason = chunk.get("done_reason") or "stop"
                        result.tokens_in = chunk.get("prompt_eval_count", 0)
                        result.tokens_out = chunk.get("eval_count", 0)
        except httpx.HTTPError as e:
            raise ProviderError(f"Ollama : {e}") from e


class GeminiAdapter:
    """API Gemini (externe). La clé n'est jamais journalisée ni renvoyée au frontend.

    Reprises automatiques sur 429 / 5xx (quota ou forte demande) avant le premier jeton.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    RETRYABLE = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        max_attempts: int = 5,
        backoff_s: float = 4.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("clé d'API Gemini manquante")
        self._key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s
        self._client = httpx.Client(transport=transport, timeout=300.0)

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._key, "content-type": "application/json"}

    def health(self) -> bool:
        try:
            return self._client.get(f"{self.base_url}/models?pageSize=1", headers=self._headers()).status_code == 200
        except httpx.HTTPError:
            return False

    @staticmethod
    def body(model: ModelSpec, messages: list[ChatMessage]) -> dict:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages
            if m.role != "system"
        ]
        body: dict = {
            "contents": contents,
            "generationConfig": {"temperature": model.temperature, "maxOutputTokens": model.max_output_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    def chat(self, model: ModelSpec, messages: list[ChatMessage], result: ChatResult) -> Iterator[str]:
        url = f"{self.base_url}/models/{model.name}:streamGenerateContent?alt=sse"
        payload = self.body(model, messages)
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self._client.stream(
                    "POST", url, headers=self._headers(), json=payload, timeout=model.timeout_s
                ) as r:
                    if r.status_code in self.RETRYABLE and attempt < self.max_attempts:
                        r.read()
                        time.sleep(self.backoff_s * attempt)
                        continue
                    if r.status_code != 200:
                        r.read()
                        raise ProviderError(f"Gemini : HTTP {r.status_code}")
                    for line in r.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = json.loads(line[6:])
                        usage = chunk.get("usageMetadata") or {}
                        result.tokens_in = usage.get("promptTokenCount", result.tokens_in)
                        result.tokens_out = usage.get("candidatesTokenCount", result.tokens_out)
                        for cand in chunk.get("candidates", [])[:1]:
                            if cand.get("finishReason"):
                                result.finish_reason = cand["finishReason"]
                            for part in cand.get("content", {}).get("parts", []):
                                if part.get("text") and not part.get("thought"):
                                    yield part["text"]
                    if result.finish_reason is None:
                        # Flux coupé sans signal de fin : la réponse est partielle, jamais présentée comme complète.
                        raise ProviderError("Gemini : flux interrompu avant la fin de la réponse")
                    return
            except httpx.HTTPError as e:
                if attempt == self.max_attempts:
                    raise ProviderError(f"Gemini : {type(e).__name__}") from e
                time.sleep(self.backoff_s * attempt)
        raise ProviderError("Gemini : indisponible après plusieurs tentatives")


class OpenAICompatibleAdapter:
    """API « chat completions » compatible OpenAI : vLLM, LM Studio, llama.cpp server (local) ou
    OpenAI et services équivalents (externe). Clé facultative, jamais journalisée."""

    def __init__(self, base_url: str, api_key: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._key = api_key
        self._client = httpx.Client(transport=transport, timeout=300.0)

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self._key}"} if self._key else {}

    def health(self) -> bool:
        try:
            return self._client.get(f"{self.base_url}/models", headers=self._headers(), timeout=10).status_code == 200
        except httpx.HTTPError:
            return False

    def chat(self, model: ModelSpec, messages: list[ChatMessage], result: ChatResult) -> Iterator[str]:
        body = {
            "model": model.name,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": model.temperature,
            "max_tokens": model.max_output_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        try:
            with self._client.stream(
                "POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=body, timeout=model.timeout_s
            ) as r:
                if r.status_code != 200:
                    r.read()
                    raise ProviderError(f"{model.name} : HTTP {r.status_code}")
                for line in r.iter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    chunk = json.loads(line[6:])
                    if chunk.get("usage"):
                        result.tokens_in = chunk["usage"].get("prompt_tokens", result.tokens_in)
                        result.tokens_out = chunk["usage"].get("completion_tokens", result.tokens_out)
                    for choice in chunk.get("choices", [])[:1]:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            yield piece
                        if choice.get("finish_reason"):
                            result.finish_reason = choice["finish_reason"]
                if result.finish_reason is None:
                    raise ProviderError(f"{model.name} : flux interrompu avant la fin de la réponse")
        except httpx.HTTPError as e:
            raise ProviderError(f"{model.name} : {type(e).__name__}") from e


@dataclass
class ModelRouter:
    adapters: dict[str, ProviderAdapter]
    models: list[ModelSpec]
    _semaphores: dict[str, threading.BoundedSemaphore] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for m in self.models:
            self._semaphores[m.id] = threading.BoundedSemaphore(m.max_concurrency)

    def candidates(
        self, policy: Policy, kinds: set[DataKind], requested: str | None = None, allow_external: bool = True
    ) -> list[ModelSpec]:
        allowed = [
            m for m in self.models if m.locality == "local" or (allow_external and policy.allows_external(kinds))
        ]
        allowed.sort(key=lambda m: (m.id != requested, m.priority))
        return allowed

    def chat(
        self,
        policy: Policy,
        kinds: set[DataKind],
        messages: list[ChatMessage],
        requested: str | None = None,
        queue_timeout_s: float = 120.0,
        allow_external: bool = True,
    ) -> tuple[ChatResult, Iterator[str]]:
        """Choisit le modèle autorisé et renvoie (résultat, flux de texte).

        Si le modèle préféré échoue avant d'avoir produit du texte, le suivant est
        essayé **uniquement** s'il est autorisé par la politique ; un modèle externe
        n'est jamais utilisé en secours si ``allow_fallback_to_external`` est faux.
        """
        models = self.candidates(policy, kinds, requested, allow_external)
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
