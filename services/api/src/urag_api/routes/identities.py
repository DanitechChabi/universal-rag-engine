"""Correspondance des comptes locaux avec les identités de la source (ADR-0016, docs/API.md §2).

Réservé à l'administrateur d'organisation : une correspondance donne accès aux
documents que l'identité externe peut lire dans la source. Les propositions
automatiques (identifiant ou courriel identique) ne donnent **aucun droit** avant
confirmation. Effet immédiat : les clés d'accès sont recalculées à chaque requête.
"""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from urag_core.audit import record

from ..deps import ORG_ADMIN, CurrentUser, get_state, problem, require
from ..state import AppState

router = APIRouter(tags=["identités externes"])


@router.get("/sources/{source_id}/identities")
def list_identities(
    source_id: uuid.UUID, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)
):
    with state.db.org(user.org_id) as conn:
        if conn.execute(text("SELECT 1 FROM sources WHERE id = :s"), {"s": source_id}).first() is None:
            raise problem(404, "source.not_found", "Source introuvable")
        rows = conn.execute(
            text("""
            SELECT ep.id, ep.kind::text AS kind, ep.external_id, ep.display_name, ep.login, ep.email, ep.synced_at,
                   u.id AS user_id, u.login AS user_login, pl.verified,
                   (SELECT count(*) FROM external_group_members m
                    WHERE m.external_group_id = ep.id OR m.external_user_id = ep.id) AS memberships
            FROM external_principals ep
            LEFT JOIN principal_links pl ON pl.external_principal_id = ep.id
            LEFT JOIN users u ON u.id = pl.user_id
            WHERE ep.source_id = :s ORDER BY ep.kind, ep.display_name NULLS LAST, ep.external_id"""),
            {"s": source_id},
        ).all()
    items = []
    for r in rows:
        link = None
        if r.user_id:
            link = {"user_id": str(r.user_id), "login": r.user_login, "verified": r.verified}
        items.append(
            {
                "id": str(r.id),
                "kind": r.kind,
                "external_id": r.external_id,
                "display_name": r.display_name,
                "login": r.login,
                "email": r.email,
                "memberships": r.memberships,
                "link": link,
            }
        )
    return {
        "items": items,
        "to_confirm": sum(1 for i in items if i["link"] and not i["link"]["verified"]),
        "unlinked_users": sum(1 for i in items if i["kind"] == "user" and not i["link"]),
    }


class LinkIn(BaseModel):
    user_id: uuid.UUID
    external_principal_id: uuid.UUID


def _link(conn, org_id: uuid.UUID, user_id: uuid.UUID, external_id: uuid.UUID) -> None:
    ok = conn.execute(
        text("""SELECT (SELECT kind::text FROM external_principals WHERE id = :x) AS kind,
                       EXISTS (SELECT 1 FROM users WHERE id = :u) AS user_ok"""),
        {"x": external_id, "u": user_id},
    ).first()
    if ok.kind is None or not ok.user_ok:
        raise problem(404, "identity.not_found", "Compte ou identité externe introuvable")
    if ok.kind != "user":
        raise problem(422, "identity.not_a_user", "Seul un utilisateur externe peut être lié à un compte")
    conn.execute(
        text("""
        INSERT INTO principal_links (org_id, user_id, external_principal_id, verified) VALUES (:o, :u, :x, true)
        ON CONFLICT (external_principal_id) DO UPDATE SET user_id = EXCLUDED.user_id, verified = true"""),
        {"o": org_id, "u": user_id, "x": external_id},
    )


@router.put("/principal-links", status_code=204)
def link(body: LinkIn, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        _link(conn, user.org_id, body.user_id, body.external_principal_id)
        record(
            conn,
            user.org_id,
            "identity.link",
            actor=user.user_id,
            target_type="external_principal",
            target_id=str(body.external_principal_id),
            details={"user_id": str(body.user_id)},
        )


@router.post("/principal-links/{external_principal_id}/confirm", status_code=204)
def confirm(
    external_principal_id: uuid.UUID,
    user: CurrentUser = Depends(require(*ORG_ADMIN)),
    state: AppState = Depends(get_state),
):
    with state.db.org(user.org_id) as conn:
        done = conn.execute(
            text("UPDATE principal_links SET verified = true WHERE external_principal_id = :x"),
            {"x": external_principal_id},
        ).rowcount
        if not done:
            raise problem(404, "identity.no_proposal", "Aucune correspondance proposée pour cette identité")
        record(
            conn,
            user.org_id,
            "identity.confirm",
            actor=user.user_id,
            target_type="external_principal",
            target_id=str(external_principal_id),
        )


@router.delete("/principal-links/{external_principal_id}", status_code=204)
def unlink(
    external_principal_id: uuid.UUID,
    user: CurrentUser = Depends(require(*ORG_ADMIN)),
    state: AppState = Depends(get_state),
):
    with state.db.org(user.org_id) as conn:
        conn.execute(text("DELETE FROM principal_links WHERE external_principal_id = :x"), {"x": external_principal_id})
        record(
            conn,
            user.org_id,
            "identity.unlink",
            actor=user.user_id,
            target_type="external_principal",
            target_id=str(external_principal_id),
        )


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=1_000_000, description="« login_local;identifiant_externe » par ligne")


@router.post("/sources/{source_id}/principal-links/import")
def import_links(
    source_id: uuid.UUID,
    body: ImportIn,
    user: CurrentUser = Depends(require(*ORG_ADMIN)),
    state: AppState = Depends(get_state),
):
    """Import en une transaction : une seule ligne invalide et rien n'est enregistré."""
    rows = [r for r in csv.reader(io.StringIO(body.csv), delimiter=";") if any(c.strip() for c in r)]
    if rows and [c.strip().lower() for c in rows[0]] == ["login_local", "identifiant_externe"]:
        rows = rows[1:]
    errors, pairs = [], []
    with state.db.org(user.org_id) as conn:
        if conn.execute(text("SELECT 1 FROM sources WHERE id = :s"), {"s": source_id}).first() is None:
            raise problem(404, "source.not_found", "Source introuvable")
        for n, r in enumerate(rows, start=1):
            if len(r) != 2:
                errors.append({"ligne": n, "erreur": "deux colonnes attendues : login_local;identifiant_externe"})
                continue
            login, external = r[0].strip(), r[1].strip()
            local = conn.execute(text("SELECT id FROM users WHERE lower(login) = lower(:l)"), {"l": login}).scalar()
            ext = conn.execute(
                text("SELECT id FROM external_principals WHERE source_id = :s AND kind = 'user' AND external_id = :x"),
                {"s": source_id, "x": external},
            ).scalar()
            if local is None:
                errors.append({"ligne": n, "erreur": f"compte local inconnu : {login}"})
            if ext is None:
                errors.append({"ligne": n, "erreur": f"utilisateur externe inconnu : {external}"})
            if local and ext:
                pairs.append((local, ext))
        if len({e for _, e in pairs}) != len(pairs):
            errors.append({"ligne": None, "erreur": "une identité externe apparaît sur plusieurs lignes"})
        if errors:
            raise problem(
                422, "identity.import_invalid", f"{len(errors)} erreur(s), rien n'a été importé : {errors[:20]}"
            )
        for local, ext in pairs:
            _link(conn, user.org_id, local, ext)
        record(
            conn,
            user.org_id,
            "identity.import",
            actor=user.user_id,
            target_type="source",
            target_id=str(source_id),
            details={"links": len(pairs)},
        )
    return {"imported": len(pairs)}
