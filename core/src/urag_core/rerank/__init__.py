"""Reclassement des passages candidats (docs/AI_MODELS.md §1, ADR-0021).

Un *cross-encoder* lit la question et chaque passage ensemble et donne un score de
pertinence ; plus précis que la similarité de vecteurs, mais plus coûteux : il ne
s'applique qu'aux premiers candidats, **après** le filtrage des droits (il ne voit
jamais un passage que l'utilisateur ne peut pas lire).

Modèle : BAAI/bge-reranker-v2-m3 (Apache-2.0), export ONNX quantifié int8, exécuté
localement avec ONNX Runtime.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class RerankError(RuntimeError):
    pass


class Reranker(Protocol):
    model_name: str

    def scores(self, query: str, passages: Sequence[str]) -> list[float]: ...


class OnnxReranker:
    def __init__(
        self,
        model_dir: str | Path,
        model_file: str = "model_int8.onnx",
        batch_size: int = 8,
        max_tokens: int = 512,
        threads: int | None = None,
    ) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_dir = Path(model_dir)
        model_path = model_dir / model_file
        if not model_path.is_file():
            raise RerankError(f"modèle de reclassement introuvable : {model_path}")
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_tokens, strategy="only_second")  # la question n'est jamais coupée
        self._tokenizer.enable_padding()
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        self.batch_size = batch_size
        self.model_name = f"bge-reranker-v2-m3-onnx-{Path(model_file).stem.removeprefix('model_') or 'fp32'}"

    def scores(self, query: str, passages: Sequence[str]) -> list[float]:
        """Probabilité de pertinence (0 à 1) de chaque passage pour la question."""
        import numpy as np

        out: list[float] = []
        for i in range(0, len(passages), self.batch_size):
            batch = self._tokenizer.encode_batch([(query, p) for p in passages[i : i + self.batch_size]])
            feed = {
                "input_ids": np.array([e.ids for e in batch], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in batch], dtype=np.int64),
            }
            logits = self._session.run(None, feed)[0][:, 0]
            out.extend(1.0 / (1.0 + math.exp(-float(x))) for x in logits)
        return out


def build_reranker(settings) -> Reranker | None:
    """``none`` (défaut) ou ``onnx`` (dossier du modèle requis)."""
    if (settings.rerank_backend or "none") == "none":
        return None
    if settings.rerank_backend == "onnx":
        return OnnxReranker(settings.rerank_model_dir)
    raise RerankError(f"reclassement inconnu : {settings.rerank_backend}")
