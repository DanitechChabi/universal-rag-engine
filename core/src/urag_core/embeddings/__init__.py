"""Encodeurs d'embeddings liés à un profil versionné (section 9.6).

- ``OllamaEncoder`` : BGE-M3 servi par Ollama (phase 1).
- ``HashingEncoder`` : encodeur déterministe sans modèle, pour les tests.
Un encodage ONNX local (sans Ollama) est prévu (docs/AI_MODELS.md §3).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

import httpx


class Encoder(Protocol):
    model_name: str
    model_revision: str
    dimension: int

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingError(Exception):
    pass


class OllamaEncoder:
    def __init__(
        self, base_url: str, model: str = "bge-m3", dimension: int = 1024, batch_size: int = 16, timeout: float = 300.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.dimension = dimension
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=timeout)
        self.model_revision = self._revision()

    def _revision(self) -> str:
        try:
            r = self._client.post(f"{self.base_url}/api/show", json={"model": self.model_name})
            r.raise_for_status()
            details = r.json()
        except httpx.HTTPError as e:
            raise EmbeddingError(f"modèle d'embedding indisponible : {e}") from e
        digest = hashlib.sha256((details.get("modelfile", "") + str(details.get("details", ""))).encode())
        return digest.hexdigest()[:12]

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = list(texts[i : i + self.batch_size])
            try:
                r = self._client.post(
                    f"{self.base_url}/api/embed", json={"model": self.model_name, "input": batch, "truncate": True}
                )
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise EmbeddingError(str(e)) from e
            embeddings = r.json().get("embeddings") or []
            if len(embeddings) != len(batch):
                raise EmbeddingError("nombre de vecteurs inattendu")
            for v in embeddings:
                if len(v) != self.dimension:
                    raise EmbeddingError(f"dimension {len(v)} au lieu de {self.dimension}")
            vectors.extend(embeddings)
        return vectors


_WORD = re.compile(r"[\wàâäéèêëîïôöùûüç]+", re.UNICODE)


class HashingEncoder:
    """Sac de mots haché, normalisé (tests uniquement : aucune compréhension du sens)."""

    model_name = "hashing"
    model_revision = "v1"

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * self.dimension
            for word in _WORD.findall(text.lower()):
                h = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "big")
                v[h % self.dimension] += 1.0 if (h >> 63) == 0 else -1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


def collection_name(model_name: str, revision: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", model_name.lower()).strip("_")
    return f"chunks_{base}_{revision}"[:64]
