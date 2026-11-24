"""Recherche, chat (SSE) et conversations (docs/API.md §2 et §3)."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from urag_core.audit import record
from urag_core.citations import pages_label
from urag_core.permissions import AccessScope
from urag_core.retrieval import SearchFilters

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
    with state.db.org(user.org_id) as conn:
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
def conversations(user: CurrentUser = Depends(require(*CAN_ASK)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        rows = conn.execute(
            text("""SELECT id, title, updated_at FROM conversations
                                    WHERE user_id = :u AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 200"""),
            {"u": user.user_id},
        ).all()
    return {"items": [{"id": str(r.id), "title": r.title, "updated_at": r.updated_at} for r in rows]}


@router.get("/conversations/{conversation_id}")
def conversation(
    conversation_id: uuid.UUID, user: CurrentUser = Depends(require(*CAN_ASK)), state: AppState = Depends(get_state)
):
    with state.db.org(user.org_id) as conn:
        conv = conn.execute(
            text("SELECT id, title, user_id FROM conversations WHERE id = :c AND deleted_at IS NULL"),
            {"c": conversation_id},
        ).first()
        if conv is None or conv.user_id != user.user_id:
            raise problem(404, "conversation.not_found", "Conversation introuvable")
        scope = AccessScope.for_user(conn, user.org_id, user.user_id)
        messages = conn.execute(
            text("""SELECT id, role::text AS role, content, insufficient, created_at
                                        FROM messages WHERE conversation_id = :c ORDER BY created_at, id"""),
            {"c": conversation_id},
        ).all()
        cites = conn.execute(
            text("""
            SELECT c.message_id, c.rank, c.document_id, c.page_start, c.page_end, c.excerpt, d.title,
                   (d.access_keys && CAST(:keys AS text[]) AND d.acl_status = 'complete'
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
                "title": c.title if c.accessible else None,
                "excerpt": c.excerpt if c.accessible else None,
                "accessible": c.accessible,
            }
        )
    return {
        "id": str(conv.id),
        "title": conv.title,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "insufficient": m.insufficient,
                "created_at": m.created_at,
                "citations": by_message.get(m.id, []),
            }
            for m in messages
        ],
    }
