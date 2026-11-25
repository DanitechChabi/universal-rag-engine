"""Qdrant : index HNSW par organisation (multi-locataire) et migration des collections existantes."""

from __future__ import annotations

import uuid

import pytest
from qdrant_client import models as qm
from urag_core.storage import VectorStore
from urag_core.storage.vectors import TENANT_HNSW, VectorPoint

from tests.integration.conftest import QDRANT_KEY, QDRANT_URL, _reachable

pytestmark = pytest.mark.skipif(_reachable() is not None, reason=str(_reachable()))


@pytest.fixture
def store():
    s = VectorStore(QDRANT_URL, QDRANT_KEY)
    name = f"test_hnsw_{uuid.uuid4().hex[:8]}"
    yield s, name
    s.client.delete_collection(name)


def test_collection_neuve_indexee_par_organisation(store):
    s, name = store
    s.ensure_collection(name, 8)
    hnsw = s.client.get_collection(name).config.hnsw_config
    assert hnsw.m == 0, "pas de graphe global : il fausse les recherches filtrées sur une organisation"
    assert hnsw.payload_m == TENANT_HNSW.payload_m


def test_collection_existante_migree(store):
    s, name = store
    s.client.create_collection(name, vectors_config=qm.VectorParams(size=8, distance=qm.Distance.COSINE))
    assert s.client.get_collection(name).config.hnsw_config.m == 16  # réglage par défaut de Qdrant
    s.ensure_collection(name, 8)
    hnsw = s.client.get_collection(name).config.hnsw_config
    assert (hnsw.m, hnsw.payload_m) == (0, TENANT_HNSW.payload_m)


def test_recherche_limitee_a_l_organisation(store):
    s, name = store
    s.ensure_collection(name, 8)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    same = [1.0, 0, 0, 0, 0, 0, 0, 0]
    for org in (org_a, org_b):
        s.upsert(
            name,
            org,
            [VectorPoint(uuid.uuid4(), same, {"org_id": str(org), "access_keys": ["g:tous"]})],
        )
    hits = s.search(name, org_a, same, ["g:tous"], 10)
    assert len(hits) == 1 and hits[0].payload["org_id"] == str(org_a)
    assert s.search(name, org_a, same, [], 10) == []  # sans clé d'accès : rien
