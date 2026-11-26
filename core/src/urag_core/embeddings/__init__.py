"""Encodeurs d'embeddings liés à un profil versionné (section 9.6).

- ``OnnxEncoder`` : BGE-M3 exporté en ONNX et quantifié int8, exécuté localement
  (ONNX Runtime) ; environ 10 fois plus rapide qu'Ollama sur CPU (ADR-0018) ;
- ``OllamaEncoder`` : BGE-M3 servi par Ollama ;
- ``HashingEncoder`` : encodeur déterministe sans modèle, pour les tests.
Chaque encodeur a son propre profil (nom + révision) : jamais de mélange de vecteurs.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from collections.abc import Sequence
from pathlib import Path
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


class OnnxEncoder:
    """BGE-M3 (vecteur dense = jeton CLS normalisé) via ONNX Runtime, sans service externe."""

    def __init__(
        self,
        model_dir: str | Path,
        model_file: str = "model_int8.onnx",
        batch_size: int = 8,
        threads: int | None = None,
        max_tokens: int = 512,
    ) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_dir = Path(model_dir)
        model_path = model_dir / model_file
        if not model_path.is_file():
            raise EmbeddingError(f"modèle ONNX introuvable : {model_path}")
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_tokens)
        self._tokenizer.enable_padding()
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        self._inputs = {i.name for i in self._session.get_inputs()}
        self._lock = threading.Lock()  # un calcul à la fois (même raison que le reclassement)
        self.batch_size = batch_size
        self.model_name = f"bge-m3-onnx-{Path(model_file).stem.removeprefix('model_') or 'fp32'}"
        self.model_revision = hashlib.sha256(f"{model_path.stat().st_size}:{max_tokens}".encode()).hexdigest()[:12]
        self.dimension = 1024

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        import numpy as np

        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = self._tokenizer.encode_batch(list(texts[i : i + self.batch_size]))
            ids = np.array([e.ids for e in batch], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": np.array([e.attention_mask for e in batch], dtype=np.int64)}
            if "token_type_ids" in self._inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            with self._lock:
                cls = self._session.run(None, feed)[0][:, 0]
            cls = cls / np.linalg.norm(cls, axis=1, keepdims=True)
            vectors.extend(cls.astype(float).tolist())
        return vectors


def build_encoder(settings) -> Encoder:
    """Encodeur selon la configuration : ``onnx`` (dossier du modèle requis) ou ``ollama``."""
    if settings.embedding_backend == "onnx":
        return OnnxEncoder(settings.embedding_model_dir)
    return OllamaEncoder(settings.ollama_url, settings.embedding_model, settings.embedding_dimension)


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
