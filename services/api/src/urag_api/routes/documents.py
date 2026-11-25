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
from urag_core.permissions import AccessScope, late_check

from ..deps import CAN_ASK, CurrentUser, get_state, problem, require
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
            WHERE d.id = :i AND d.deleted_at IS NULL AND d.access_keys && CAST(:keys AS text[])"""),
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
