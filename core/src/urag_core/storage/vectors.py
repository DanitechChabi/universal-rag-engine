"""Qdrant : vecteurs + champs de filtre, sans texte (ADR-0005).

Aucune recherche n'est possible sans organisation, et une recherche sans clé
d'accès renvoie une liste vide (fermé par défaut).
"""

from __future__ import annotations

import uuid
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client import models as qm


@dataclass(frozen=True)
class VectorPoint:
    id: uuid.UUID
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorHit:
    id: uuid.UUID
    score: float
    payload: dict[str, Any]


# Index HNSW par organisation (documentation Qdrant, « Multitenancy ») : pas de graphe global
# (m=0), un graphe par valeur de org_id (payload_m). Avec un graphe global, une recherche
# filtrée sur une organisation parmi plusieurs perd des résultats (mesuré : le bon passage
# passait du rang 1 à au-delà du rang 30 dès qu'une deuxième organisation était présente).
TENANT_HNSW = qm.HnswConfigDiff(m=0, payload_m=16)
UPSERT_BATCH = 256  # points par requête d'écriture


class VectorStore:
    def __init__(self, url: str, api_key: str | None = None, timeout: int = 30) -> None:
        with warnings.catch_warnings():
            # HTTP sans TLS attendu sur le réseau interne de Docker (Qdrant non publié, ADR-0025) ;
            # l'avertissement du client répété à chaque démarrage n'apporte rien.
            warnings.filterwarnings("ignore", "Api key is used with an insecure connection")
            self.client = QdrantClient(url=url, api_key=api_key, timeout=timeout, https=url.startswith("https"))

    def ensure_collection(self, name: str, dimension: int) -> None:
        if self.client.collection_exists(name):
            info = self.client.get_collection(name)
            size = info.config.params.vectors.size  # type: ignore[union-attr]
            if size != dimension:
                raise ValueError(f"collection {name} : dimension {size}, {dimension} attendue")
            hnsw = info.config.hnsw_config
            if hnsw.m != 0 or hnsw.payload_m != TENANT_HNSW.payload_m:  # collection créée avant ce réglage
                self.client.update_collection(name, hnsw_config=TENANT_HNSW)
            return
        self.client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE, on_disk=True),
            hnsw_config=TENANT_HNSW,
            quantization_config=qm.ScalarQuantization(
                scalar=qm.ScalarQuantizationConfig(type=qm.ScalarType.INT8, always_ram=True)
            ),
        )
        self.client.create_payload_index(
            name, "org_id", field_schema=qm.KeywordIndexParams(type=qm.KeywordIndexType.KEYWORD, is_tenant=True)
        )
        for key in ("access_keys", "deny_keys", "document_id", "version_id", "source_id", "space_id", "doc_class"):
            self.client.create_payload_index(name, key, field_schema=qm.PayloadSchemaType.KEYWORD)

    @staticmethod
    def _org_filter(org_id: uuid.UUID, *must: qm.Condition) -> qm.Filter:
        return qm.Filter(must=[qm.FieldCondition(key="org_id", match=qm.MatchValue(value=str(org_id))), *must])

    def upsert(self, collection: str, org_id: uuid.UUID, points: Sequence[VectorPoint]) -> None:
        if not points:
            return
        for p in points:
            if p.payload.get("org_id") != str(org_id):
                raise ValueError("point sans l'organisation attendue")
        # Par lots : un gros document (plus de mille fragments) envoyé d'un bloc dépassait le délai
        # de 30 s sur une machine chargée (OCR en parallèle) — trouvé en phase 7 sur le corpus public.
        for start in range(0, len(points), UPSERT_BATCH):
            self.client.upsert(
                collection_name=collection,
                points=[
                    qm.PointStruct(id=str(p.id), vector=p.vector, payload=p.payload)
                    for p in points[start : start + UPSERT_BATCH]
                ],
                wait=True,
            )

    def search(
        self,
        collection: str,
        org_id: uuid.UUID,
        vector: list[float],
        access_keys: Sequence[str],
        limit: int,
        source_ids: Sequence[uuid.UUID] | None = None,
        doc_classes: Sequence[str] | None = None,
    ) -> list[VectorHit]:
        if not access_keys:
            return []
        must: list[qm.Condition] = [qm.FieldCondition(key="access_keys", match=qm.MatchAny(any=list(access_keys)))]
        if source_ids:
            must.append(qm.FieldCondition(key="source_id", match=qm.MatchAny(any=[str(s) for s in source_ids])))
        if doc_classes:
            must.append(qm.FieldCondition(key="doc_class", match=qm.MatchAny(any=list(doc_classes))))
        query_filter = self._org_filter(org_id, *must)
        # Refus explicite (ADR-0020) : une clé de refus commune exclut le point.
        query_filter.must_not = [qm.FieldCondition(key="deny_keys", match=qm.MatchAny(any=list(access_keys)))]
        result = self.client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [VectorHit(uuid.UUID(str(p.id)), p.score, p.payload or {}) for p in result.points]

    def delete_where(self, collection: str, org_id: uuid.UUID, key: str, value: uuid.UUID) -> None:
        cond = qm.FieldCondition(key=key, match=qm.MatchValue(value=str(value)))
        self.client.delete(
            collection_name=collection,
            points_selector=qm.FilterSelector(filter=self._org_filter(org_id, cond)),
            wait=True,
        )

    def set_access_keys(
        self,
        collection: str,
        org_id: uuid.UUID,
        document_id: uuid.UUID,
        keys: Sequence[str],
        deny_keys: Sequence[str] = (),
    ) -> None:
        cond = qm.FieldCondition(key="document_id", match=qm.MatchValue(value=str(document_id)))
        self.client.set_payload(
            collection_name=collection,
            payload={"access_keys": list(keys), "deny_keys": list(deny_keys)},
            points=qm.FilterSelector(filter=self._org_filter(org_id, cond)),
            wait=True,
        )

    def count(self, collection: str, org_id: uuid.UUID) -> int:
        return self.client.count(collection, count_filter=self._org_filter(org_id), exact=True).count
