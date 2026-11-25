"""Tableau de bord (cahier des charges §10.3) et compléments d'administration (§10.7).

Le tableau de bord ne renvoie que des compteurs et des évènements résumés : jamais de contenu
documentaire, ni le texte des questions (journalisé selon la décision Q5, lisible seulement par
les auditeurs).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from urag_core.audit import record

from ..deps import DOC_ADMIN, ORG_ADMIN, CurrentUser, get_state, problem, require
from ..state import AppState
from .admin import health

router = APIRouter(tags=["administration"])


@router.get("/admin/dashboard")
def dashboard(user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        sources = conn.execute(
            text("SELECT count(*) FILTER (WHERE enabled), count(*) FILTER (WHERE status = 'error') FROM sources")
        ).one()
        docs = dict(
            conn.execute(
                text("SELECT status::text, count(*) FROM documents WHERE deleted_at IS NULL GROUP BY status")
            ).all()
        )
        fragments = conn.execute(
            text("""SELECT coalesce(sum(v.chunk_count), 0) FROM documents d
                    JOIN document_versions v ON v.id = d.current_version_id WHERE d.deleted_at IS NULL""")
        ).scalar_one()
        jobs = conn.execute(
            text("""SELECT count(*) FILTER (WHERE status = 'queued'), count(*) FILTER (WHERE status = 'running'),
                           count(*) FILTER (WHERE status = 'failed' AND finished_at > now() - interval '1 day')
                    FROM jobs""")
        ).one()
        usage = conn.execute(
            text("""SELECT count(*), count(*) FILTER (WHERE locality = 'external'),
                           coalesce(sum(tokens_in), 0), coalesce(sum(tokens_out), 0)
                    FROM messages WHERE role = 'assistant' AND created_at > now() - interval '30 days'""")
        ).one()
        policy = conn.execute(text("SELECT mode::text FROM ai_policies WHERE org_id = :o"), {"o": user.org_id}).scalar()
        activity = conn.execute(
            text("""SELECT a.action, a.outcome, a.target_type, a.created_at, u.display_name AS actor
                    FROM audit_log a LEFT JOIN users u ON u.id = a.actor_user_id
                    ORDER BY a.id DESC LIMIT 12""")
        ).all()
    model = state.router.models[0] if state.router.models else None
    return {
        "sources": {"active": sources[0], "error": sources[1]},
        "documents": {"by_status": docs, "total": sum(docs.values()), "failed": docs.get("failed", 0)},
        "fragments": fragments,
        "jobs": {"queued": jobs[0], "running": jobs[1], "failed_24h": jobs[2]},
        "services": health(state)["services"],
        "model": {"name": model.name, "locality": model.locality} if model else None,
        "policy": policy or "local_only",
        "usage_30d": {"answers": usage[0], "external": usage[1], "tokens_in": usage[2], "tokens_out": usage[3]},
        "activity": [
            {
                "action": a.action,
                "outcome": a.outcome,
                "target_type": a.target_type,
                "at": a.created_at,
                "actor": a.actor,
            }
            for a in activity
        ],
    }


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    roles: list[Literal["org_admin", "doc_admin", "user", "auditor"]] | None = None
    status: Literal["active", "disabled"] | None = None


@router.patch("/users/{user_id}", status_code=204)
def update_user(
    user_id: uuid.UUID,
    body: UserPatch,
    user: CurrentUser = Depends(require(*ORG_ADMIN)),
    state: AppState = Depends(get_state),
):
    if user_id == user.user_id and (
        body.status == "disabled" or (body.roles is not None and "org_admin" not in body.roles)
    ):
        raise problem(
            422, "user.self_lockout", "Vous ne pouvez ni vous désactiver ni retirer votre propre rôle d'administrateur"
        )
    with state.db.org(user.org_id) as conn:
        if conn.execute(text("SELECT 1 FROM users WHERE id = :u"), {"u": user_id}).first() is None:
            raise problem(404, "user.not_found", "Utilisateur introuvable")
        if body.display_name is not None:
            conn.execute(
                text("UPDATE users SET display_name = :d WHERE id = :u"), {"d": body.display_name, "u": user_id}
            )
        if body.status is not None:
            conn.execute(
                text("UPDATE users SET status = CAST(:s AS account_status) WHERE id = :u"),
                {"s": body.status, "u": user_id},
            )
            if body.status == "disabled":  # sessions révoquées immédiatement (docs/SECURITY.md §3)
                conn.execute(
                    text("UPDATE sessions SET revoked_at = now() WHERE user_id = :u AND revoked_at IS NULL"),
                    {"u": user_id},
                )
        if body.roles is not None:
            conn.execute(text("DELETE FROM user_roles WHERE user_id = :u"), {"u": user_id})
            for role in sorted(set(body.roles)):
                conn.execute(
                    text("INSERT INTO user_roles (org_id, user_id, role) VALUES (:o, :u, CAST(:r AS user_role))"),
                    {"o": user.org_id, "u": user_id, "r": role},
                )
        record(
            conn,
            user.org_id,
            "user.update",
            actor=user.user_id,
            target_type="user",
            target_id=str(user_id),
            details=body.model_dump(exclude_none=True),
        )


@router.get("/spaces")
def list_spaces(user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        spaces = conn.execute(
            text("""SELECT s.id, s.name, s.description,
                           (SELECT count(*) FROM sources x WHERE x.space_id = s.id) AS sources
                    FROM spaces s ORDER BY s.name""")
        ).all()
        grants = conn.execute(
            text("""SELECT g.space_id, g.principal_type::text AS type, g.principal_id,
                           coalesce(u.display_name, gr.name) AS name
                    FROM space_grants g
                    LEFT JOIN users u ON g.principal_type = 'user' AND u.id = g.principal_id
                    LEFT JOIN groups gr ON g.principal_type = 'group' AND gr.id = g.principal_id""")
        ).all()
    by_space: dict = {}
    for g in grants:
        by_space.setdefault(g.space_id, []).append(
            {"principal_type": g.type, "principal_id": str(g.principal_id), "name": g.name}
        )
    return {
        "items": [
            {
                "id": str(s.id),
                "name": s.name,
                "description": s.description,
                "sources": s.sources,
                "grants": by_space.get(s.id, []),
            }
            for s in spaces
        ]
    }
