"""Recherche, chat (SSE) et conversations (docs/API.md §2 et §3)."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from urag_core.audit import record
from urag_core.citations import pages_label
from urag_core.permissions import AccessScope
from urag_core.retrieval import SearchBusy, SearchFilters

from ..deps import CAN_ASK, CurrentUser, get_state, problem, require
from ..state import AppState

router = APIRouter(tags=["recherche"])


class Filters(BaseModel):
    source_ids: list[uuid.UUID] = Field(default_factory=list)
    doc_classes: list[str] = Field(default_factory=list)

    def to_core(self) -> SearchFilters:
        return SearchFilters(tuple(self.source_ids), tuple(self.doc_classes))


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)
    filters: Filters = Field(default_factory=Filters)


@router.post("/search")
def search(body: SearchIn, user: CurrentUser = Depends(require(*CAN_ASK)), state: AppState = Depends(get_state)):
    try:
        with state.retriever.admit(), state.db.org(user.org_id) as conn:
            scope = AccessScope.for_user(conn, user.org_id, user.user_id)
            passages = state.retriever.search(
                conn,
                scope,
                body.query,
                limit=body.limit,
                candidates=state.settings.retrieval_candidates,
                filters=body.filters.to_core(),
            )
            record(conn, user.org_id, "search.query", actor=user.user_id, details={"results": len(passages)})
    except SearchBusy:
        raise problem(503, "search.busy", "Serveur occupé : réessayez dans un instant") from None
    return {
        "items": [
            {
                "chunk_id": str(p.chunk_id),
                "document_id": str(p.document_id),
                "title": p.title,
                "source": p.source_name,
                "pages": pages_label(p),
                "section": list(p.section_path),
                "excerpt": p.text[:600],
                "score": round(p.score, 5),
                "suspect": p.suspicious,
                "channels": list(p.channels),
            }
            for p in passages
        ]
    }


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    model_id: str | None = None
    filters: Filters = Field(default_factory=Filters)


MASKED = "Réponse masquée : un document qu'elle cite ne vous est plus accessible."


def _pages(start: int | None, end: int | None) -> str:
    if start is None:
        return ""
    return f"page {start}" if end in (None, start) else f"pages {start}-{end}"


def _sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat")
def chat(body: ChatIn, user: CurrentUser = Depends(require(*CAN_ASK)), state: AppState = Depends(get_state)):
    if body.conversation_id is not None:
        with state.db.org(user.org_id) as conn:
            owner = conn.execute(
                text("SELECT user_id FROM conversations WHERE id = :c AND deleted_at IS NULL"),
                {"c": body.conversation_id},
            ).scalar_one_or_none()
        if owner != user.user_id:
            raise problem(404, "conversation.not_found", "Conversation introuvable")
    events = state.rag.answer(
        user.org_id, user.user_id, body.question, body.conversation_id, body.filters.to_core(), body.model_id
    )
    return StreamingResponse(
        (_sse(e.name, e.data) for e in events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
def conversations(
    q: str | None = Query(default=None, max_length=200),
    user: CurrentUser = Depends(require(*CAN_ASK)),
    state: AppState = Depends(get_state),
):
    """Ses conversations ; ``q`` : recherche littérale dans les titres et dans ses propres questions
    (jamais dans les réponses, qui peuvent reprendre un document devenu inaccessible)."""
    like = "%" + (q or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with state.db.org(user.org_id) as conn:
        rows = conn.execute(
            text("""SELECT c.id, c.title, c.updated_at FROM conversations c
                    WHERE c.user_id = :u AND c.deleted_at IS NULL
                      AND (CAST(:q AS text) IS NULL
                           OR c.title ILIKE :like ESCAPE '\\'
                           OR EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id AND m.role = 'user'
                                      AND m.content ILIKE :like ESCAPE '\\'))
                    ORDER BY c.updated_at DESC LIMIT 200"""),
            {"u": user.user_id, "q": q.strip() if q and q.strip() else None, "like": like},
        ).all()
    return {"items": [{"id": str(r.id), "title": r.title, "updated_at": r.updated_at} for r in rows]}


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _own_conversation(conn, conversation_id: uuid.UUID, user: CurrentUser):
    conv = conn.execute(
        text("SELECT id, title, user_id FROM conversations WHERE id = :c AND deleted_at IS NULL"),
        {"c": conversation_id},
    ).first()
    if conv is None or conv.user_id != user.user_id:
        raise problem(404, "conversation.not_found", "Conversation introuvable")
    return conv


@router.patch("/conversations/{conversation_id}", status_code=204)
def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationPatch,
    user: CurrentUser = Depends(require(*CAN_ASK)),
    state: AppState = Depends(get_state),
):
    with state.db.org(user.org_id) as conn:
        _own_conversation(conn, conversation_id, user)
        conn.execute(
            text("UPDATE conversations SET title = :t WHERE id = :c"), {"t": body.title.strip(), "c": conversation_id}
        )


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser = Depends(require(*CAN_ASK)), state: AppState = Depends(get_state)
):
    """Suppression réelle : messages et citations effacés (cascade) ; l'audit garde la trace de l'action."""
    with state.db.org(user.org_id) as conn:
        _own_conversation(conn, conversation_id, user)
        conn.execute(text("DELETE FROM conversations WHERE id = :c"), {"c": conversation_id})
        record(
            conn,
            user.org_id,
            "conversation.delete",
            actor=user.user_id,
            target_type="conversation",
            target_id=str(conversation_id),
        )


@router.get("/conversations/{conversation_id}")
def conversation(
    conversation_id: uuid.UUID, user: CurrentUser = Depends(require(*CAN_ASK)), state: AppState = Depends(get_state)
):
    with state.db.org(user.org_id) as conn:
        conv = _own_conversation(conn, conversation_id, user)
        scope = AccessScope.for_user(conn, user.org_id, user.user_id)
        messages = conn.execute(
            text("""SELECT id, role::text AS role, content, insufficient, created_at, locality::text AS locality
                                        FROM messages WHERE conversation_id = :c ORDER BY created_at, id"""),
            {"c": conversation_id},
        ).all()
        cites = conn.execute(
            text("""
            SELECT c.message_id, c.rank, c.document_id, c.page_start, c.page_end, c.excerpt, d.title,
                   (urag_doc_visible(d.access_keys, d.deny_keys, CAST(:keys AS text[])) AND d.acl_status = 'complete'
                    AND d.deleted_at IS NULL) AS accessible
            FROM citations c JOIN documents d ON d.id = c.document_id
            WHERE c.message_id = ANY(CAST(:ids AS uuid[])) ORDER BY c.rank"""),
            {"keys": list(scope.keys), "ids": [str(m.id) for m in messages]},
        ).all()
    by_message: dict = {}
    for c in cites:
        # Droits revérifiés : un document devenu inaccessible n'affiche plus son extrait.
        by_message.setdefault(c.message_id, []).append(
            {
                "rank": c.rank,
                "document_id": str(c.document_id),
                "pages": _pages(c.page_start, c.page_end) if c.accessible else None,
                "title": c.title if c.accessible else None,
                "excerpt": c.excerpt if c.accessible else None,
                "accessible": c.accessible,
            }
        )
    # §8.4 : une réponse qui cite un document devenu inaccessible n'est plus affichée (son texte peut
    # reprendre le contenu du document) ; la question de l'utilisateur reste visible.
    masked = {mid for mid, items in by_message.items() if any(not c["accessible"] for c in items)}
    return {
        "id": str(conv.id),
        "title": conv.title,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": MASKED if m.id in masked else m.content,
                "masked": m.id in masked,
                "insufficient": m.insufficient,
                "locality": m.locality,
                "created_at": m.created_at,
                "citations": by_message.get(m.id, []),
            }
            for m in messages
        ],
    }
