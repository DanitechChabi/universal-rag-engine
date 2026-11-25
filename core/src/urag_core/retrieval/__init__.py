"""Recherche hybride filtrée (ADR-0007, docs/SECURITY.md §2.3).

1. Canal dense : Qdrant, filtré par organisation + clés d'accès.
2. Canal lexical : plein texte PostgreSQL + références exactes, sur
   ``searchable_chunks`` filtré par les mêmes clés.
3. Fusion par rang réciproque (RRF).
4. Relecture des passages retenus dans ``searchable_chunks`` : revérifie version
   courante, suppression et droits (un retard de Qdrant ne peut qu'exclure).
5. Revérification auprès de la source (droits effectifs) quand elle le permet.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from ..embeddings import Encoder
from ..extraction import detect_language
from ..permissions import AccessScope, late_check
from ..storage import VectorStore

RRF_K = 60
_REFERENCE = re.compile(r"\b(?=[\w./-]*\d)(?=[\w./-]*[a-zA-Z])[\w][\w./-]{3,}\b|\b\d[\d ./-]{4,}\d\b")


@dataclass(frozen=True)
class SearchFilters:
    source_ids: tuple[uuid.UUID, ...] = ()
    doc_classes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Passage:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    source_id: uuid.UUID
    source_name: str
    text: str
    page_start: int | None
    page_end: int | None
    section_path: tuple[str, ...]
    source_version: str | None
    score: float
    channels: tuple[str, ...] = field(default_factory=tuple)
    suspicious: str | None = None  # raison, si le passage contient des consignes adressées à une IA


def rrf(rankings: dict[str, list[uuid.UUID]], k: int = RRF_K) -> list[tuple[uuid.UUID, float, tuple[str, ...]]]:
    """Fusion déterministe : somme de 1 / (k + rang) sur les canaux."""
    scores: dict[uuid.UUID, float] = {}
    channels: dict[uuid.UUID, list[str]] = {}
    for name, ids in rankings.items():
        for rank, cid in enumerate(ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            channels.setdefault(cid, []).append(name)
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return [(cid, score, tuple(channels[cid])) for cid, score in ordered]


def references_in(query: str) -> list[str]:
    """Références exactes probables : numéros de dossier, de contrat, montants."""
    return list(dict.fromkeys(m.group(0).strip() for m in _REFERENCE.finditer(query)))[:5]


class Retriever:
    def __init__(self, vectors: VectorStore, encoder: Encoder, collection: str, late_check: bool = True) -> None:
        self.vectors = vectors
        self.encoder = encoder
        self.collection = collection
        self.late_check = late_check  # revérification auprès des sources qui le permettent

    def dense(self, scope: AccessScope, query: str, limit: int, filters: SearchFilters) -> list[uuid.UUID]:
        vector = self.encoder.encode([query])[0]
        hits = self.vectors.search(
            self.collection,
            scope.org_id,
            vector,
            scope.keys,
            limit,
            source_ids=filters.source_ids or None,
            doc_classes=filters.doc_classes or None,
        )
        return [h.id for h in hits]

    @staticmethod
    def lexical(
        conn: Connection, scope: AccessScope, query: str, limit: int, filters: SearchFilters
    ) -> list[uuid.UUID]:
        if not scope.keys:
            return []
        config = "english" if detect_language(query) == "en" else "urag_fr"
        params = {
            "keys": list(scope.keys),
            "q": query,
            "lim": limit,
            "src": [str(s) for s in filters.source_ids] or None,
            "cls": list(filters.doc_classes) or None,
        }
        common = """urag_doc_visible(access_keys, deny_keys, CAST(:keys AS text[]))
                    AND (CAST(:src AS uuid[]) IS NULL OR source_id = ANY(CAST(:src AS uuid[])))
                    AND (CAST(:cls AS text[]) IS NULL OR doc_class = ANY(CAST(:cls AS text[])))"""
        rows = (
            conn.execute(
                text(f"""
            SELECT id FROM searchable_chunks
            WHERE {common} AND tsv @@ websearch_to_tsquery('{config}', :q)
            ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('{config}', :q)) DESC, id
            LIMIT :lim"""),
                params,
            )
            .scalars()
            .all()
        )
        exact: list[uuid.UUID] = []
        for i, ref in enumerate(references_in(query)):
            params[f"r{i}"] = f"%{ref}%"
            exact += (
                conn.execute(
                    text(f"""
                SELECT id FROM searchable_chunks WHERE {common} AND text ILIKE :r{i}
                ORDER BY id LIMIT :lim"""),
                    params,
                )
                .scalars()
                .all()
            )
        # Les correspondances exactes passent devant.
        return list(dict.fromkeys([*exact, *rows]))[:limit]

    @staticmethod
    def load(
        conn: Connection, scope: AccessScope, ranked: list[tuple[uuid.UUID, float, tuple[str, ...]]]
    ) -> list[Passage]:
        """Relit les passages en revérifiant les droits ; conserve l'ordre de la fusion."""
        if not ranked or not scope.keys:
            return []
        rows = conn.execute(
            text("""
            SELECT c.id, c.document_id, c.version_id, c.title, c.source_id, s.name AS source_name, c.text,
                   c.page_start, c.page_end, c.section_path, d.source_version, c.suspicious_reason
            FROM searchable_chunks c
            JOIN sources s ON s.id = c.source_id
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = ANY(CAST(:ids AS uuid[]))
              AND urag_doc_visible(c.access_keys, c.deny_keys, CAST(:keys AS text[]))"""),
            {"ids": [str(cid) for cid, _, _ in ranked], "keys": list(scope.keys)},
        ).all()
        by_id = {r.id: r for r in rows}
        passages = []
        for cid, score, channels in ranked:
            r = by_id.get(cid)
            if r is None:
                continue  # supprimé, ancienne version, droits retirés : exclu
            passages.append(
                Passage(
                    r.id,
                    r.document_id,
                    r.version_id,
                    r.title,
                    r.source_id,
                    r.source_name,
                    r.text,
                    r.page_start,
                    r.page_end,
                    tuple(r.section_path or ()),
                    r.source_version,
                    score,
                    channels,
                    r.suspicious_reason,
                )
            )
        return passages

    def search(
        self,
        conn: Connection,
        scope: AccessScope,
        query: str,
        limit: int = 10,
        candidates: int = 30,
        filters: SearchFilters | None = None,
    ) -> list[Passage]:
        filters = filters or SearchFilters()
        if not scope.keys or not query.strip():
            return []
        ranked = rrf(
            {
                "dense": self.dense(scope, query, candidates, filters),
                "lexical": self.lexical(conn, scope, query, candidates, filters),
            }
        )
        passages = self.load(conn, scope, ranked[:candidates])
        if self.late_check and passages:
            allowed = late_check(conn, scope, list(dict.fromkeys(p.document_id for p in passages)))
            passages = [p for p in passages if p.document_id in allowed]
        return passages[:limit]
