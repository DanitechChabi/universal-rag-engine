"""Reclassement des candidats (ADR-0021)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from urag_core.retrieval import Passage, Retriever

MODEL_DIR = Path(os.environ.get("URAG_TEST_RERANK_MODEL_DIR", "/home/user/urag-models/bge-reranker-v2-m3-onnx"))


def _passage(text: str, context: str | None = None) -> Passage:
    return Passage(
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        "doc",
        uuid.uuid4(),
        "source",
        text,
        1,
        1,
        (),
        "1",
        0.1,
        ("dense",),
        None,
        context,
    )


class FakeReranker:
    model_name = "faux"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def scores(self, query, passages):
        self.seen = list(passages)
        return [float("Bénin" in p) for p in passages]


def test_reclassement_ordre_et_contexte():
    fake = FakeReranker()
    r = Retriever(None, None, "c", late_check=False, reranker=fake, rerank_candidates=3)
    a, b, c, d = _passage("liste A"), _passage("liste B", "Liste Bénin 2026"), _passage("liste C"), _passage("hors")
    ranked = r.rerank("établissements au Bénin", [a, b, c, d])
    assert [p.text for p in ranked] == ["liste B", "liste A", "liste C", "hors"]  # au-delà des 3 : inchangé
    assert fake.seen[1] == "Liste Bénin 2026\nliste B"  # le contexte du document est lu par le modèle
    assert ranked[0].score == 1.0 and "rerank" in ranked[0].channels


@pytest.mark.skipif(not (MODEL_DIR / "model_int8.onnx").is_file(), reason="modèle de reclassement absent")
def test_modele_distingue_le_pays():
    from urag_core.rerank import OnnxReranker

    scores = OnnxReranker(MODEL_DIR).scores(
        "Quels établissements de monnaie électronique sont agréés au Bénin ?",
        [
            "ETABLISSEMENTS DE MONNAIE ELECTRONIQUE (3)\n1 MOOV MONEY BENIN\n2 MTN MOBILE MONEY BENIN",
            "ETABLISSEMENTS DE MONNAIE ELECTRONIQUE (2)\n1 ORANGE MONEY COTE D'IVOIRE\n2 WAVE COTE D'IVOIRE",
            "Le capital social minimum des banques est de 20 milliards de FCFA.",
        ],
    )
    assert scores[0] > 0.5 > scores[1] and scores[0] > scores[2]
