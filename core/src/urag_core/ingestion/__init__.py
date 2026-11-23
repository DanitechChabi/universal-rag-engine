"""Ingestion : synchronisation d'une source et indexation d'un document (docs/ARCHITECTURE.md §4.1).

- ``sync_source`` : liste la source, met à jour les documents (idempotent par
  ``(source_id, external_id)``), calcule les droits, marque les disparus comme
  supprimés et crée une tâche ``ingest_document`` par document nouveau ou modifié.
- ``ingest_document`` : télécharge, calcule l'empreinte, extrait, découpe, encode,
  écrit la version et les fragments, publie les vecteurs, puis bascule la version
  courante de façon atomique. Un échec ne concerne que ce document.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text
from urag_connectors_base import (
    AccessDeniedError,
    BaseConnector,
    ConnectorError,
    NotFoundError,
    UnsupportedError,
    load_connector_class,
)

from ..chunking import ChunkingProfile, chunk_document
from ..embeddings import Encoder, collection_name
from ..extraction import ExtractionError, UnsupportedFormatError, detect_language, extract
from ..jobs import enqueue
from ..permissions import document_keys
from ..storage import Database, VectorPoint, VectorStore

log = logging.getLogger(__name__)


@dataclass
class SyncReport:
    seen: int = 0
    queued: int = 0
    unchanged: int = 0
    deleted: int = 0
    access_changed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class IngestReport:
    document_id: uuid.UUID
    status: str
    chunks: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class EmbeddingProfile:
    id: uuid.UUID
    collection: str
    dimension: int


class IngestionService:
    def __init__(self, db: Database, vectors: VectorStore, encoder: Encoder, tmp_dir: Path,
                 chunking: ChunkingProfile | None = None) -> None:
        self.db = db
        self.vectors = vectors
        self.encoder = encoder
        self.tmp_dir = tmp_dir
        self.chunking = chunking or ChunkingProfile()
        self._profile: EmbeddingProfile | None = None

    # -------------------------------------------------------------- profil

    def profile(self, conn: Connection) -> EmbeddingProfile:
        """Profil d'embedding de l'encodeur ; créé et activé s'il n'existe aucun profil actif."""
        if self._profile is not None:
            return self._profile
        name = collection_name(self.encoder.model_name, self.encoder.model_revision)
        row = conn.execute(text("""
            SELECT id, collection_name, dimension FROM embedding_profiles
            WHERE model_name = :m AND model_revision = :r"""),
            {"m": self.encoder.model_name, "r": self.encoder.model_revision}).first()
        if row is None:
            has_active = conn.execute(text("SELECT EXISTS (SELECT 1 FROM embedding_profiles "
                                           "WHERE state = 'active')")).scalar_one()
            row = conn.execute(text("""
                INSERT INTO embedding_profiles (model_name, model_revision, dimension, collection_name, state)
                VALUES (:m, :r, :d, :c, CAST(:s AS embedding_state))
                ON CONFLICT (model_name, model_revision) DO UPDATE SET model_name = EXCLUDED.model_name
                RETURNING id, collection_name, dimension"""),
                {"m": self.encoder.model_name, "r": self.encoder.model_revision, "d": self.encoder.dimension,
                 "c": name, "s": "building" if has_active else "active"}).first()
        self.vectors.ensure_collection(row.collection_name, row.dimension)
        self._profile = EmbeddingProfile(row.id, row.collection_name, row.dimension)
        return self._profile

    # -------------------------------------------------------------- source

    @staticmethod
    def _source(conn: Connection, source_id: uuid.UUID) -> Any:
        row = conn.execute(text("""
            SELECT id, org_id, space_id, kind::text AS kind, config, inherit_space_access, enabled
            FROM sources WHERE id = :s"""), {"s": source_id}).first()
        if row is None:
            raise LookupError(f"source introuvable : {source_id}")
        return row

    @staticmethod
    def connector_for(source: Any) -> BaseConnector:
        cls = load_connector_class(source.kind)
        return cls(dict(source.config))

    def _external_ids(self, conn: Connection, source_id: uuid.UUID) -> dict:
        from urag_connectors_base import ExternalPrincipalRef

        rows = conn.execute(text("SELECT id, kind::text, external_id FROM external_principals "
                                 "WHERE source_id = :s"), {"s": source_id})
        return {ExternalPrincipalRef(r.kind, r.external_id): r.id for r in rows}

    def sync_source(self, org_id: uuid.UUID, source_id: uuid.UUID) -> SyncReport:
        report = SyncReport()
        with self.db.org(org_id) as conn:
            source = self._source(conn, source_id)
            if not source.enabled:
                raise UnsupportedError("source désactivée")
            profile = self.profile(conn)
        connector = self.connector_for(source)
        with connector:
            documents = list(connector.list_documents())
            accesses = {a.ref.external_id: a for a in connector.get_access([d.ref for d in documents])}

        with self.db.org(org_id) as conn:
            external_ids = self._external_ids(conn, source_id)
            seen: list[str] = []
            for doc in documents:
                report.seen += 1
                seen.append(doc.ref.external_id)
                keys = document_keys(accesses[doc.ref.external_id], source.space_id,
                                     source.inherit_space_access, external_ids)
                row = conn.execute(text("""
                    INSERT INTO documents (org_id, source_id, external_id, title, filename, extension, mime_type,
                        size_bytes, source_created_at, source_modified_at, source_version, author, doc_class,
                        location, metadata, source_metadata, access_keys, acl_status, acl_snapshot, acl_synced_at)
                    VALUES (:o, :s, :x, :t, :fn, :ext, :mime, :size, :cr, :mo, :v, :au, :dc, :loc,
                        CAST(:md AS jsonb), CAST(:smd AS jsonb), CAST(:keys AS text[]), CAST(:acl AS acl_status),
                        CAST(:snap AS jsonb), now())
                    ON CONFLICT (source_id, external_id) DO UPDATE SET
                        title = EXCLUDED.title, filename = EXCLUDED.filename, extension = EXCLUDED.extension,
                        mime_type = EXCLUDED.mime_type, size_bytes = EXCLUDED.size_bytes,
                        source_modified_at = EXCLUDED.source_modified_at, author = EXCLUDED.author,
                        doc_class = EXCLUDED.doc_class, location = EXCLUDED.location,
                        metadata = EXCLUDED.metadata, source_metadata = EXCLUDED.source_metadata,
                        access_keys = EXCLUDED.access_keys, acl_status = EXCLUDED.acl_status,
                        acl_snapshot = EXCLUDED.acl_snapshot, acl_synced_at = now(), deleted_at = NULL,
                        source_version = EXCLUDED.source_version, updated_at = now()
                    RETURNING id, status::text AS status, current_version_id,
                        (xmax = 0) AS inserted,
                        (SELECT d.source_version FROM documents d WHERE d.id = documents.id) AS old_version,
                        (SELECT d.access_keys FROM documents d WHERE d.id = documents.id) AS old_keys,
                        (SELECT d.deleted_at FROM documents d WHERE d.id = documents.id) AS old_deleted"""),
                    {"o": org_id, "s": source_id, "x": doc.ref.external_id, "t": doc.title[:500],
                     "fn": doc.filename, "ext": doc.extension, "mime": doc.mime_type, "size": doc.size_bytes,
                     "cr": doc.created_at, "mo": doc.modified_at, "v": doc.ref.version, "au": doc.author,
                     "dc": doc.doc_class, "loc": doc.location, "md": json.dumps(doc.metadata, default=str),
                     "smd": json.dumps(doc.source_metadata, default=str), "keys": list(keys.keys),
                     "acl": "complete" if keys.complete else "uncertain",
                     "snap": json.dumps({"reason": keys.reason, **accesses[doc.ref.external_id].raw},
                                        default=str)}).first()
                changed = (row.inserted or row.old_version != doc.ref.version or row.old_deleted is not None
                           or row.status not in ("indexed", "indexed_with_warning"))
                if changed:
                    if enqueue(conn, org_id, "ingest_document", {"document_id": str(row.id)},
                               dedup_key=f"ingest:{row.id}", priority=50) is not None:
                        report.queued += 1
                else:
                    report.unchanged += 1
                    if list(row.old_keys or []) != list(keys.keys) and row.current_version_id:
                        report.access_changed += 1
                        self.vectors.set_access_keys(profile.collection, org_id, row.id, keys.keys)

            # Disparus de la source : retirés de l'index (jamais supprimés de la source).
            gone = conn.execute(text("""
                UPDATE documents SET deleted_at = now(), status = 'deleted', updated_at = now()
                WHERE source_id = :s AND deleted_at IS NULL AND NOT (external_id = ANY(CAST(:seen AS text[])))
                RETURNING id"""), {"s": source_id, "seen": seen}).scalars().all()
            for doc_id in gone:
                self.vectors.delete_where(profile.collection, org_id, "document_id", doc_id)
            report.deleted = len(gone)
            conn.execute(text("""UPDATE sources SET last_sync_at = now(), last_sync_status = :st,
                                 status = 'active', updated_at = now() WHERE id = :s"""),
                         {"s": source_id, "st": json.dumps(report.__dict__, default=str)})
        return report

    # -------------------------------------------------------------- document

    def _set_status(self, org_id: uuid.UUID, document_id: uuid.UUID, status: str, detail: str | None) -> None:
        with self.db.org(org_id) as conn:
            conn.execute(text("UPDATE documents SET status = CAST(:st AS index_status), status_detail = :d, "
                              "updated_at = now() WHERE id = :i"),
                         {"st": status, "d": detail, "i": document_id})

    def ingest_document(self, org_id: uuid.UUID, document_id: uuid.UUID) -> IngestReport:
        work_dir = self.tmp_dir / f"ingest-{uuid.uuid4().hex}"
        try:
            return self._ingest(org_id, document_id, work_dir)
        except (UnsupportedError, UnsupportedFormatError, AccessDeniedError) as e:
            self._set_status(org_id, document_id, "excluded", str(e))
            return IngestReport(document_id, "excluded", detail=str(e))
        except NotFoundError as e:
            self._set_status(org_id, document_id, "deleted", "introuvable dans la source")
            return IngestReport(document_id, "deleted", detail=str(e))
        except (ExtractionError, ConnectorError) as e:
            self._set_status(org_id, document_id, "failed", str(e))
            return IngestReport(document_id, "failed", detail=str(e))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)  # fichiers temporaires toujours supprimés

    def _ingest(self, org_id: uuid.UUID, document_id: uuid.UUID, work_dir: Path) -> IngestReport:
        with self.db.org(org_id) as conn:
            doc = conn.execute(text("""
                SELECT d.id, d.external_id, d.source_version, d.title, d.doc_class, d.access_keys,
                       d.current_version_id, d.deleted_at, s.id AS source_id, s.space_id, s.kind::text AS kind,
                       s.config
                FROM documents d JOIN sources s ON s.id = d.source_id WHERE d.id = :i"""),
                {"i": document_id}).first()
            if doc is None or doc.deleted_at is not None:
                return IngestReport(document_id, "deleted")
            profile = self.profile(conn)
            conn.execute(text("UPDATE documents SET status = 'processing', updated_at = now() WHERE id = :i"),
                         {"i": document_id})

        from urag_connectors_base import DocumentRef

        connector = load_connector_class(doc.kind)(dict(doc.config))
        with connector:
            fetched = connector.fetch_content(DocumentRef(doc.external_id, doc.source_version), work_dir)
        digest = hashlib.sha256(fetched.path.read_bytes()).digest()

        with self.db.org(org_id) as conn:
            same = conn.execute(text("""
                SELECT id, chunk_count FROM document_versions
                WHERE document_id = :d AND sha256 = :h AND embedding_profile_id = :p AND status IN
                ('indexed', 'indexed_with_warning')"""), {"d": document_id, "h": digest, "p": profile.id}).first()
            if same is not None and same.id == doc.current_version_id:
                conn.execute(text("UPDATE documents SET status = 'indexed', sha256 = :h, updated_at = now() "
                                  "WHERE id = :i AND status = 'processing'"), {"h": digest, "i": document_id})
                return IngestReport(document_id, "unchanged", same.chunk_count)

        extracted = extract(fetched.path)
        drafts = chunk_document(extracted, self.chunking)
        if not drafts:
            detail = "aucun texte extractible" + (" (document scanné : OCR en phase 2)"
                                                  if extracted.pages_without_text else "")
            self._set_status(org_id, document_id, "failed", detail)
            return IngestReport(document_id, "failed", detail=detail)
        language = detect_language(extracted.text)
        vectors = self.encoder.encode([d.embedding_text(doc.title) for d in drafts])
        status = "indexed_with_warning" if extracted.warnings and extracted.pages_without_text else "indexed"

        # 1. Version et fragments écrits, version pas encore courante (invisible à la recherche).
        with self.db.org(org_id) as conn:
            conn.execute(text("DELETE FROM document_versions WHERE document_id = :d AND sha256 = :h "
                              "AND embedding_profile_id = :p AND id IS DISTINCT FROM :cur"),
                         {"d": document_id, "h": digest, "p": profile.id, "cur": doc.current_version_id})
            version_id = conn.execute(text("""
                INSERT INTO document_versions (org_id, document_id, source_version, sha256, embedding_profile_id,
                    extractor, page_count, chunk_count, language, status, warnings)
                VALUES (:o, :d, :sv, :h, :p, :ex, :pc, :cc, :lang, 'processing', CAST(:w AS jsonb))
                RETURNING id"""),
                {"o": org_id, "d": document_id, "sv": doc.source_version, "h": digest, "p": profile.id,
                 "ex": extracted.extractor, "pc": extracted.page_count, "cc": len(drafts), "lang": language,
                 "w": json.dumps(extracted.warnings)}).scalar_one()
            chunk_ids = [
                conn.execute(text("""
                    INSERT INTO chunks (org_id, document_id, version_id, ordinal, text, page_start, page_end,
                        section_path, kind, language, token_count)
                    VALUES (:o, :d, :v, :n, :t, :ps, :pe, CAST(:sp AS text[]), :k, :lang, :tc) RETURNING id"""),
                    {"o": org_id, "d": document_id, "v": version_id, "n": d.ordinal, "t": d.text,
                     "ps": d.page_start, "pe": d.page_end, "sp": list(d.section_path) or None, "k": d.kind,
                     "lang": language, "tc": len(d.text) // 4}).scalar_one()
                for d in drafts
            ]

        # 2. Vecteurs publiés (encore filtrés par la version courante côté PostgreSQL).
        payload_base = {"org_id": str(org_id), "document_id": str(document_id), "version_id": str(version_id),
                        "source_id": str(doc.source_id), "space_id": str(doc.space_id),
                        "doc_class": doc.doc_class or "", "language": language,
                        "access_keys": list(doc.access_keys or [])}
        try:
            self.vectors.upsert(profile.collection, org_id, [
                VectorPoint(cid, vec, payload_base) for cid, vec in zip(chunk_ids, vectors, strict=True)])
        except Exception as e:
            with self.db.org(org_id) as conn:
                conn.execute(text("UPDATE document_versions SET status = 'failed', error = :e WHERE id = :v"),
                             {"e": str(e)[:2000], "v": version_id})
            self.vectors.delete_where(profile.collection, org_id, "version_id", version_id)
            raise ConnectorError(f"indexation vectorielle impossible : {e}") from e

        # 3. Bascule atomique : la nouvelle version devient courante, l'ancienne est invalidée.
        with self.db.org(org_id) as conn:
            conn.execute(text("UPDATE document_versions SET status = CAST(:st AS index_status), indexed_at = now() "
                              "WHERE id = :v"), {"st": status, "v": version_id})
            conn.execute(text("UPDATE document_versions SET superseded_at = now() "
                              "WHERE document_id = :d AND id <> :v AND superseded_at IS NULL"),
                         {"d": document_id, "v": version_id})
            conn.execute(text("""UPDATE documents SET current_version_id = :v, status = CAST(:st AS index_status),
                                 status_detail = :det, sha256 = :h, updated_at = now() WHERE id = :d"""),
                         {"v": version_id, "st": status, "h": digest, "d": document_id,
                          "det": "; ".join(extracted.warnings) or None})
        if doc.current_version_id is not None:
            self.vectors.delete_where(profile.collection, org_id, "version_id", doc.current_version_id)
        return IngestReport(document_id, status, len(drafts))
