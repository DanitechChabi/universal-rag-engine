"""Comportement sous charge : calculs ONNX un à la fois, admission des recherches (phase 7)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from urag_core.retrieval import Retriever, SearchBusy


class _Session:
    """Fausse session ONNX qui relève le nombre maximal de calculs simultanés."""

    def __init__(self, *shape: int) -> None:
        self.active = self.peak = 0
        self.shape = shape  # dimensions de la sortie après le lot
        self.guard = threading.Lock()

    def run(self, _outputs, feed):
        with self.guard:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.02)
        with self.guard:
            self.active -= 1
        return [np.ones((len(feed["input_ids"]), *self.shape), dtype=np.float32)]


class _Encoding:
    ids = [1, 2, 3]
    attention_mask = [1, 1, 1]


class _Tokenizer:
    def encode_batch(self, items):
        return [_Encoding() for _ in items]


def _parallel(fn, n=6):
    with ThreadPoolExecutor(n) as ex:
        list(ex.map(lambda _: fn(), range(n)))


def test_reclassement_un_calcul_a_la_fois():
    from urag_core.rerank import OnnxReranker

    r = object.__new__(OnnxReranker)
    r._tokenizer, r._session, r._lock, r.batch_size = _Tokenizer(), _Session(1), threading.Lock(), 8
    _parallel(lambda: r.scores("q", ["a"] * 16))
    assert r._session.peak == 1


def test_encodeur_un_calcul_a_la_fois():
    from urag_core.embeddings import OnnxEncoder

    e = object.__new__(OnnxEncoder)
    e._tokenizer, e._session, e._lock, e.batch_size = _Tokenizer(), _Session(3, 4), threading.Lock(), 8
    e._inputs = {"input_ids", "attention_mask"}
    _parallel(lambda: e.encode(["a"] * 16))
    assert e._session.peak == 1


def test_admission_limitee_puis_refus():
    r = Retriever(None, None, "c", concurrency=2, queue_timeout=0.1)
    with r.admit(), r.admit():
        t = time.perf_counter()
        with pytest.raises(SearchBusy), r.admit():
            pass
        assert time.perf_counter() - t >= 0.09  # attend avant de refuser
    with r.admit():  # places rendues, y compris après un refus
        pass


def test_options_onnx_pour_serveur_partage():
    from urag_core.config import Settings
    from urag_core.embeddings import api_onnx_threads, onnx_options

    o = onnx_options(2)
    assert o.enable_cpu_mem_arena is False and o.intra_op_num_threads == 2
    assert o.get_session_config_entry("session.intra_op.allow_spinning") == "0"
    import os

    cores = os.cpu_count() or 1
    assert api_onnx_threads(Settings(api_workers=2)) == max(1, cores // 2)  # cœurs partagés entre processus
    assert api_onnx_threads(Settings(api_workers=64)) == 1
    assert api_onnx_threads(Settings(api_workers=2, onnx_threads=3)) == 3  # valeur imposée


def test_bombe_de_decompression_refusee(tmp_path):
    import zipfile

    from urag_core.extraction import UnsupportedFormatError, extract

    bomb = tmp_path / "piege.docx"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", b"\0" * (64 * 2**20))  # 64 Mo de zéros : ~64 Ko compressés
    assert bomb.stat().st_size < 2**20
    with pytest.raises(UnsupportedFormatError, match="compression anormal"):
        extract(bomb)
