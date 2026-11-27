"""Utilisateurs, espaces, sources, documents, tâches, santé (docs/API.md §2)."""

from __future__ import annotations

import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from urag_connectors_base import AccessDeniedError, ConnectorError, load_connector_class
from urag_core.audit import record
from urag_core.jobs import enqueue
from urag_core.security import WeakPasswordError

from ..deps import DOC_ADMIN, ORG_ADMIN, CurrentUser, get_state, problem, require
from ..state import AppState

router = APIRouter(tags=["administration"])
SECRET_FIELDS = {"password", "api_key", "token", "secret", "credentials"}

# ------------------------------------------------------------------ utilisateurs


class UserIn(BaseModel):
    login: str = Field(min_length=2, max_length=120)
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    password: str = Field(min_length=1, max_length=1024)
    roles: list[Literal["org_admin", "doc_admin", "user", "auditor"]] = ["user"]


@router.post("/users", status_code=201)
def create_user(body: UserIn, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)):
    try:
        password_hash = state.hasher.hash(body.password)
    except WeakPasswordError as e:
        raise problem(422, "user.weak_password", f"Mot de passe trop faible : {e}") from e
    try:
        with state.db.org(user.org_id) as conn:
            uid = conn.execute(
                text("""INSERT INTO users (org_id, login, display_name, email, password_hash)
                                       VALUES (:o, :l, :d, :e, :p) RETURNING id"""),
                {"o": user.org_id, "l": body.login, "d": body.display_name, "e": body.email, "p": password_hash},
            ).scalar_one()
            for role in set(body.roles):
                conn.execute(
                    text("INSERT INTO user_roles (org_id, user_id, role) VALUES (:o, :u, CAST(:r AS user_role))"),
                    {"o": user.org_id, "u": uid, "r": role},
                )
            record(
                conn,
                user.org_id,
                "user.create",
                actor=user.user_id,
                target_type="user",
                target_id=str(uid),
                details={"roles": sorted(set(body.roles))},
            )
    except IntegrityError as e:
        raise problem(409, "user.exists", "Cet identifiant est déjà utilisé") from e
    return {"id": str(uid)}


@router.get("/users")
def list_users(user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        rows = conn.execute(
            text("""SELECT u.id, u.login, u.display_name, u.status::text AS status,
                           coalesce(array_agg(r.role::text) FILTER (WHERE r.role IS NOT NULL), '{}') AS roles
                    FROM users u LEFT JOIN user_roles r ON r.user_id = u.id
                    GROUP BY u.id ORDER BY u.login""")
        ).all()
    return {
        "items": [
            {
                "id": str(r.id),
                "login": r.login,
                "display_name": r.display_name,
                "status": r.status,
                "roles": sorted(r.roles),
            }
            for r in rows
        ]
    }


# ------------------------------------------------------------------ espaces


class SpaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class Grant(BaseModel):
    principal_type: Literal["user", "group"]
    principal_id: uuid.UUID


@router.post("/spaces", status_code=201)
def create_space(body: SpaceIn, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        sid = conn.execute(
            text("INSERT INTO spaces (org_id, name, description) VALUES (:o, :n, :d) RETURNING id"),
            {"o": user.org_id, "n": body.name, "d": body.description},
        ).scalar_one()
        record(conn, user.org_id, "space.create", actor=user.user_id, target_type="space", target_id=str(sid))
    return {"id": str(sid)}


@router.put("/spaces/{space_id}/grants")
def set_grants(
    space_id: uuid.UUID,
    grants: list[Grant],
    user: CurrentUser = Depends(require(*ORG_ADMIN)),
    state: AppState = Depends(get_state),
):
    with state.db.org(user.org_id) as conn:
        if conn.execute(text("SELECT 1 FROM spaces WHERE id = :s"), {"s": space_id}).first() is None:
            raise problem(404, "space.not_found", "Espace introuvable")
        for g in grants:  # le principal doit appartenir à l'organisation
            table = "users" if g.principal_type == "user" else "groups"
            if conn.execute(text(f"SELECT 1 FROM {table} WHERE id = :i"), {"i": g.principal_id}).first() is None:
                raise problem(422, "space.bad_principal", "Utilisateur ou groupe inconnu")
        conn.execute(text("DELETE FROM space_grants WHERE space_id = :s"), {"s": space_id})
        for g in grants:
            conn.execute(
                text("""INSERT INTO space_grants (org_id, space_id, principal_type, principal_id)
                                 VALUES (:o, :s, CAST(:t AS principal_kind), :p)"""),
                {"o": user.org_id, "s": space_id, "t": g.principal_type, "p": g.principal_id},
            )
        record(
            conn,
            user.org_id,
            "space.grants",
            actor=user.user_id,
            target_type="space",
            target_id=str(space_id),
            details={"count": len(grants)},
        )
    return {"count": len(grants)}


# ------------------------------------------------------------------ sources


class SourceIn(BaseModel):
    kind: Literal["local_files", "mfiles", "simulator"]
    name: str = Field(min_length=1, max_length=200)
    space_id: uuid.UUID
    config: dict = Field(default_factory=dict)
    inherit_space_access: bool = False  # décision Q9 : fermé par défaut


@router.post("/sources", status_code=201)
def create_source(
    body: SourceIn, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    if SECRET_FIELDS & {k.lower() for k in body.config}:
        raise problem(422, "source.secret_in_config", "Les identifiants se saisissent à part (chiffrés)")
    if body.kind == "local_files":
        # Contrôle des dossiers autorisés par l'installation (refait par le worker à chaque usage).
        try:
            load_connector_class(body.kind)(dict(body.config))
        except AccessDeniedError as e:
            raise problem(422, "source.root_not_allowed", str(e)) from None
        except ConnectorError as e:
            raise problem(422, "source.bad_config", str(e)) from None
    with state.db.org(user.org_id) as conn:
        if conn.execute(text("SELECT 1 FROM spaces WHERE id = :s"), {"s": body.space_id}).first() is None:
            raise problem(422, "source.bad_space", "Espace inconnu")
        sid = conn.execute(
            text("""
            INSERT INTO sources (org_id, space_id, kind, name, config, inherit_space_access)
            VALUES (:o, :sp, CAST(:k AS source_kind), :n, CAST(:c AS jsonb), :inh) RETURNING id"""),
            {
                "o": user.org_id,
                "sp": body.space_id,
                "k": body.kind,
                "n": body.name,
                "c": json.dumps(body.config),
                "inh": body.inherit_space_access,
            },
        ).scalar_one()
        record(
            conn,
            user.org_id,
            "source.create",
            actor=user.user_id,
            target_type="source",
            target_id=str(sid),
            details={"kind": body.kind},
        )
    return {"id": str(sid)}


@router.get("/sources")
def list_sources(user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        rows = conn.execute(
            text("""
            SELECT s.id, s.name, s.kind::text AS kind, s.status::text AS status, s.enabled, s.last_sync_at,
                   s.inherit_space_access,
                   count(d.id) FILTER (WHERE d.deleted_at IS NULL) AS documents,
                   count(d.id) FILTER (WHERE d.status = 'failed') AS errors
            FROM sources s LEFT JOIN documents d ON d.source_id = s.id GROUP BY s.id ORDER BY s.name""")
        ).all()
    return {
        "items": [
            {
                "id": str(r.id),
                "name": r.name,
                "kind": r.kind,
                "status": r.status,
                "enabled": r.enabled,
                "last_sync_at": r.last_sync_at,
                "documents": r.documents,
                "errors": r.errors,
                "inherit_space_access": r.inherit_space_access,
            }
            for r in rows
        ]
    }


def _source_row(conn, source_id):
    row = conn.execute(
        text("SELECT id, kind::text AS kind, config FROM sources WHERE id = :s"), {"s": source_id}
    ).first()
    if row is None:
        raise problem(404, "source.not_found", "Source introuvable")
    return row


@router.get("/sources/{source_id}")
def source_detail(
    source_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    """Configuration sans secret (les identifiants chiffrés ne sont jamais renvoyés)."""
    with state.db.org(user.org_id) as conn:
        r = conn.execute(
            text("""
            SELECT s.id, s.name, s.kind::text AS kind, s.status::text AS status, s.enabled, s.config,
                   s.inherit_space_access, s.last_sync_at, s.last_sync_status, s.secret_id, s.space_id,
                   sp.name AS space, s.sync_cursor IS NOT NULL AS incremental
            FROM sources s JOIN spaces sp ON sp.id = s.space_id WHERE s.id = :s"""),
            {"s": source_id},
        ).first()
    if r is None:
        raise problem(404, "source.not_found", "Source introuvable")
    try:
        last = json.loads(r.last_sync_status) if r.last_sync_status else None
    except ValueError:
        last = None
    return {
        "id": str(r.id),
        "name": r.name,
        "kind": r.kind,
        "status": r.status,
        "enabled": r.enabled,
        "config": {k: v for k, v in (r.config or {}).items() if k.lower() not in SECRET_FIELDS},
        "credentials_configured": r.secret_id is not None,
        "inherit_space_access": r.inherit_space_access,
        "space": {"id": str(r.space_id), "name": r.space},
        "last_sync_at": r.last_sync_at,
        "last_sync": last,
        "incremental": r.incremental,
    }


@router.post("/sources/{source_id}/disable", status_code=204)
def disable_source(
    source_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    """Plus aucune synchronisation ; les documents déjà indexés restent consultables."""
    _set_enabled(state, user, source_id, False)


@router.post("/sources/{source_id}/enable", status_code=204)
def enable_source(
    source_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    _set_enabled(state, user, source_id, True)


def _set_enabled(state: AppState, user: CurrentUser, source_id: uuid.UUID, enabled: bool) -> None:
    with state.db.org(user.org_id) as conn:
        _source_row(conn, source_id)
        conn.execute(
            text(
                "UPDATE sources SET enabled = :e, status = CAST(:st AS source_status), updated_at = now() WHERE id = :s"
            ),
            {"e": enabled, "st": "active" if enabled else "disabled", "s": source_id},
        )
        record(
            conn,
            user.org_id,
            "source.enable" if enabled else "source.disable",
            actor=user.user_id,
            target_type="source",
            target_id=str(source_id),
        )


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(
    source_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    """Retire la source et tous ses documents de l'index. **Ne touche jamais la source d'origine.**"""
    with state.db.org(user.org_id) as conn:
        _source_row(conn, source_id)
        collection = state.ingestion.profile(conn).collection
        conn.execute(text("DELETE FROM jobs WHERE payload->>'source_id' = :s"), {"s": str(source_id)})
        conn.execute(text("DELETE FROM sources WHERE id = :s"), {"s": source_id})  # documents, fragments en cascade
        record(conn, user.org_id, "source.delete", actor=user.user_id, target_type="source", target_id=str(source_id))
    state.vectors.delete_where(collection, user.org_id, "source_id", source_id)


@router.post("/sources/{source_id}/test")
def test_source(
    source_id: uuid.UUID, user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)
):
    with state.db.org(user.org_id) as conn:
        row = _source_row(conn, source_id)
    try:
        connector = load_connector_class(row.kind)(dict(row.config))
        with connector:
            report = connector.test_connection()
    except ConnectorError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": report.ok, "message": report.message, "details": report.details}


class SyncIn(BaseModel):
    mode: Literal["auto", "incremental", "full"] = "auto"


@router.post("/sources/{source_id}/sync", status_code=202)
def sync_source(
    source_id: uuid.UUID,
    body: SyncIn | None = None,
    user: CurrentUser = Depends(require(*DOC_ADMIN)),
    state: AppState = Depends(get_state),
):
    """``auto`` (défaut) : incrémental si possible ; ``full`` : liste complète de contrôle."""
    mode = (body or SyncIn()).mode
    with state.db.org(user.org_id) as conn:
        _source_row(conn, source_id)
        if not conn.execute(text("SELECT enabled FROM sources WHERE id = :s"), {"s": source_id}).scalar_one():
            raise problem(409, "source.disabled", "Source désactivée : réactivez-la avant de la synchroniser")
        job_id = enqueue(
            conn,
            user.org_id,
            "sync_source",
            {"source_id": str(source_id), "mode": "full" if mode == "full" else "auto"},
            dedup_key=f"sync:{source_id}",
            priority=20,
        )
        record(
            conn,
            user.org_id,
            "source.sync",
            actor=user.user_id,
            target_type="source",
            target_id=str(source_id),
            details={"mode": mode},
        )
    return {"job_id": job_id, "already_queued": job_id is None}


# ------------------------------------------------------------------ documents et tâches


@router.get("/admin/jobs")
def list_jobs(user: CurrentUser = Depends(require(*DOC_ADMIN)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        rows = conn.execute(
            text("""SELECT id, kind, status::text AS status, attempts, progress, last_error,
                                           created_at, finished_at FROM jobs ORDER BY id DESC LIMIT 200""")
        ).all()
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/admin/health")
def health(state: AppState = Depends(get_state)):
    checks = {}
    try:
        with state.db.anonymous() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:  # noqa: BLE001 - état de santé, sans détail technique
        checks["postgres"] = "error"
    try:
        state.vectors.client.get_collections()
        checks["qdrant"] = "ok"
    except Exception:  # noqa: BLE001
        checks["qdrant"] = "error"
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "services": checks}
