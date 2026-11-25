"""Ouverture du document original (scénario de recette 7, docs/API.md §2).

Les droits sont **revérifiés** au moment de l'ouverture (clés d'accès recalculées) ;
un document absent, supprimé ou non autorisé donne la même réponse 404, pour ne
pas révéler son existence. Le fichier est relu dans la source (jamais une copie
conservée par la RAG) et servi dans un bac à sable (CSP ``sandbox``).
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import text
from starlette.background import BackgroundTask
from urag_connectors_base import ConnectorError, DocumentRef, NotFoundError, load_connector_class
from urag_core.audit import record
from urag_core.jobs import enqueue
from urag_core.permissions import AccessScope, late_check

from ..deps import CAN_ASK, DOC_ADMIN, CurrentUser, get_state, problem, require
from ..state import AppState

router = APIRouter(tags=["documents"])

# Types affichés dans le navigateur ; tout le reste est proposé au téléchargement.
INLINE = {"application/pdf", "image/png", "image/jpeg", "text/plain"}
SANDBOX_CSP = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; object-src 'self'"


@router.get("/documents/{document_id}/open")
def open_document(
    document_id: uuid.UUID, user: CurrentUser = Depends(require(*CAN_ASK)), state: AppState = Depends(get_state)
):
    with state.db.org(user.org_id) as conn:
        scope = AccessScope.for_user(conn, user.org_id, user.user_id)
        doc = conn.execute(
            text("""
            SELECT d.id, d.external_id, d.source_version, d.title, d.filename, d.mime_type,
                   s.kind::text AS kind, s.config
            FROM documents d JOIN sources s ON s.id = d.source_id
            WHERE d.id = :i AND d.deleted_at IS NULL AND d.acl_status = 'complete'
              AND urag_doc_visible(d.access_keys, d.deny_keys, CAST(:keys AS text[]))"""),
            {"i": document_id, "keys": list(scope.keys)},
        ).first()
        if doc is not None and state.settings.late_access_check and not late_check(conn, scope, [doc.id]):
            doc = None  # droit retiré dans la source depuis la dernière synchronisation
        if doc is None:
            record(
                conn,
                user.org_id,
                "document.open_denied",
                actor=user.user_id,
                target_type="document",
                target_id=str(document_id),
            )
    if doc is None:
        raise problem(404, "document.not_found", "Document introuvable")

    connector = load_connector_class(doc.kind)(dict(doc.config))
    ref = DocumentRef(doc.external_id, doc.source_version)
    state.settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="urag-open-", dir=state.settings.tmp_dir))
    try:
        with connector:
            link = connector.external_link(ref)
            fetched = None if link else connector.fetch_content(ref, work)
    except NotFoundError:
        shutil.rmtree(work, ignore_errors=True)
        raise problem(404, "document.not_found", "Document introuvable") from None
    except ConnectorError:
        shutil.rmtree(work, ignore_errors=True)
        raise problem(502, "source.unavailable", "La source du document est indisponible") from None

    with state.db.org(user.org_id) as conn:
        record(conn, user.org_id, "document.open", actor=user.user_id, target_type="document", target_id=str(doc.id))
    if link:
        shutil.rmtree(work, ignore_errors=True)
        return RedirectResponse(link, status_code=303)

    mime = fetched.mime_type or doc.mime_type or "application/octet-stream"
    filename = doc.filename or f"{doc.title}{fetched.path.suffix}"
    return FileResponse(
        fetched.path,
        media_type=mime,
        filename=filename,
        content_disposition_type="inline" if mime in INLINE else "attachment",
        headers={"Content-Security-Policy": SANDBOX_CSP, "Cache-Control": "no-store"},
        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True),
    )


# ------------------------------------------------------------------ administration des documents
# Métadonnées et état d'indexation seulement : jamais le contenu (docs/API.md §2).

DOC_COLUMNS = """
    d.id, d.title, d.filename, d.extension, d.status::text AS status, d.status_detail,
    d.acl_status::text AS acl_status, cardinality(d.access_keys) AS access_key_count,
    cardinality(d.deny_keys) AS deny_key_count, d.excluded, d.source_modified_at, d.source_version,
    d.updated_at, s.id AS source_id, s.name AS source, v.chunk_count"""


def _doc_item(r) -> dict:
    return {
        "id": str(r.id),
        "title": r.title,
        "filename": r.filename,
        "extension": r.extension,
        "status": r.status,
        "status_detail": r.status_detail,
        "acl_status": r.acl_status,
        "access_key_count": r.access_key_count,
        "deny_key_count": r.deny_key_count,
        "excluded": r.excluded,
        "source_modified_at": r.source_modified_at,
        "source_version": r.source_version,
        "updated_at": r.updated_at,
        "source_id": str(r.source_id),
        "source": r.source,
        "chunk_count": r.chunk_count,
    }


@router.get("/documents")
def list_documents(
    status: str | None = None,
    source_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
    user: CurrentUser = Depends(require(*DOC_ADMIN)),
    state: AppState = Depends(get_state),
):
    limit, offset = max(1, min(limit, 500)), max(0, offset)
    where = """d.deleted_at IS NULL AND (CAST(:st AS text) IS NULL OR d.status::text = :st)
               AND (CAST(:src AS uuid) IS NULL OR d.source_id = :src)
               AND (CAST(:q AS text) IS NULL
                    OR d.title ILIKE :like ESCAPE '\\' OR d.filename ILIKE :like ESCAPE '\\')"""
    params = {
        "st": status,
        "src": str(source_id) if source_id else None,
        "q": q or None,
        # Recherche littérale : « % » et « _ » saisis ne sont pas des jokers SQL.
        "like": "%" + (q or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
    }
    with state.db.org(user.org_id) as conn:
        total = conn.execute(text(f"SELECT count(*) FROM documents d WHERE {where}"), params).scalar_one()
        rows = conn.execute(
            text(f"""
            SELECT {DOC_COLUMNS}
            FROM documents d JOIN sources s ON s.id = d.source_id
            LEFT JOIN document_versions v ON v.id = d.current_version_id
            WHERE {where} ORDER BY d.title, d.id LIMIT :lim OFFSET :off"""),
            {**params, "lim": limit, "off": offset},
        ).all()
        counts = dict(
            conn.execute(
                text("SELECT status::text, count(*) FROM documents WHERE deleted_at IS NULL GROUP BY status")
            ).all()
        )
    return {"items": [_doc_item(r) for r in rows], "total": total, "by_status": counts}


def _document_or_404(conn, document_id: uuid.UUID):
    row = conn.execute(
        text(f"""
        SELECT {DOC_COLUMNS}, d.acl_snapshot, d.acl_synced_at, d.metadata, d.location, d.author, d.doc_class,
               d.mime_type, d.size_bytes, d.current_version_id
        FROM documents d JOIN sources s ON s.id = d.source_id
        LEFT JOIN document_versions v ON v.id = d.current_version_id
        WHERE d.id = :i AND d.deleted_at IS NULL"""),
        {"i": document_id},
    ).first()
    if row is None:
        raise problem(404, "document.not_found", "Document introuvable")
    return row


@router.get("/documents/{document_id}")
def document_detail(
    document_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    with state.db.org(user.org_id) as conn:
        r = _document_or_404(conn, document_id)
        versions = conn.execute(
            text("""
            SELECT id, source_version, status::text AS status, chunk_count, page_count, language, extractor,
                   ocr_engine, ocr_min_confidence, warnings, error, created_at, indexed_at, superseded_at,
                   pipeline_version, context
            FROM document_versions WHERE document_id = :i ORDER BY created_at DESC LIMIT 20"""),
            {"i": document_id},
        ).all()
    snapshot = r.acl_snapshot or {}
    return _doc_item(r) | {
        "mime_type": r.mime_type,
        "size_bytes": r.size_bytes,
        "author": r.author,
        "doc_class": r.doc_class,
        "location": r.location,
        "metadata": r.metadata,
        "access": {
            "status": r.acl_status,
            "keys": r.access_key_count,
            "deny_keys": r.deny_key_count,
            "reason": snapshot.get("reason"),
            "synced_at": r.acl_synced_at,
        },
        "versions": [
            {
                "id": str(v.id),
                "current": v.id == r.current_version_id,
                "source_version": v.source_version,
                "status": v.status,
                "chunk_count": v.chunk_count,
                "page_count": v.page_count,
                "language": v.language,
                "extractor": v.extractor,
                "ocr_engine": v.ocr_engine,
                "ocr_min_confidence": v.ocr_min_confidence,
                "warnings": v.warnings,
                "error": v.error,
                "created_at": v.created_at,
                "indexed_at": v.indexed_at,
                "superseded_at": v.superseded_at,
                "pipeline_version": v.pipeline_version,
                "context": v.context,
            }
            for v in versions
        ],
    }


@router.post("/documents/{document_id}/reindex", status_code=202)
def reindex(
    document_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    """Relance le traitement ; un contenu identique déjà indexé avec le même traitement reste inchangé."""
    with state.db.org(user.org_id) as conn:
        _document_or_404(conn, document_id)
        job_id = enqueue(
            conn,
            user.org_id,
            "ingest_document",
            {"document_id": str(document_id)},
            dedup_key=f"ingest:{document_id}",
            priority=30,
        )
        record(
            conn,
            user.org_id,
            "document.reindex",
            actor=user.user_id,
            target_type="document",
            target_id=str(document_id),
        )
    return {"job_id": job_id, "already_queued": job_id is None}


@router.post("/documents/{document_id}/exclude", status_code=204)
def exclude(
    document_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    """Retiré des recherches et des réponses immédiatement ; l'index est conservé (réintégration rapide)."""
    _set_excluded(state, user, document_id, True)


@router.post("/documents/{document_id}/include", status_code=204)
def include(
    document_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    _set_excluded(state, user, document_id, False)


def _set_excluded(state: AppState, user: CurrentUser, document_id: uuid.UUID, excluded: bool) -> None:
    with state.db.org(user.org_id) as conn:
        doc = _document_or_404(conn, document_id)
        conn.execute(
            text("UPDATE documents SET excluded = :e, updated_at = now() WHERE id = :i"),
            {"e": excluded, "i": document_id},
        )
        if not excluded and doc.current_version_id is None:  # retiré de l'index : on le réindexe
            conn.execute(text("UPDATE documents SET status = 'pending' WHERE id = :i"), {"i": document_id})
            enqueue(
                conn,
                user.org_id,
                "ingest_document",
                {"document_id": str(document_id)},
                dedup_key=f"ingest:{document_id}",
                priority=30,
            )
        record(
            conn,
            user.org_id,
            "document.exclude" if excluded else "document.include",
            actor=user.user_id,
            target_type="document",
            target_id=str(document_id),
        )


@router.delete("/documents/{document_id}/index", status_code=204)
def remove_from_index(
    document_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    """Retire le document de l'index (fragments et vecteurs supprimés) et l'exclut des synchronisations
    suivantes. **Le document original n'est jamais touché** dans sa source."""
    with state.db.org(user.org_id) as conn:
        _document_or_404(conn, document_id)
        conn.execute(
            text("""UPDATE documents SET excluded = true, current_version_id = NULL, status = 'excluded',
                    status_detail = 'retiré de l''index par un administrateur', updated_at = now() WHERE id = :i"""),
            {"i": document_id},
        )
        conn.execute(text("DELETE FROM document_versions WHERE document_id = :i"), {"i": document_id})
        collection = state.ingestion.profile(conn).collection
        record(
            conn,
            user.org_id,
            "document.remove_from_index",
            actor=user.user_id,
            target_type="document",
            target_id=str(document_id),
        )
    state.vectors.delete_where(collection, user.org_id, "document_id", document_id)
