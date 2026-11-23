"""Authentification (docs/API.md, ADR-0011)."""

from __future__ import annotations

import ipaddress
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from urag_core.audit import record
from urag_core.security import AccessClaims, TokenService, hash_refresh_token

from ..deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    CurrentUser,
    current_user,
    get_state,
    problem,
)
from ..state import AppState

router = APIRouter(prefix="/auth", tags=["auth"])
INVALID = ("auth.invalid", "Identifiant ou mot de passe incorrect")  # même message pour tous les cas


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


def _client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def _open_session(conn, state: AppState, org_id, user_id, family_id, request) -> tuple[str, str, list[str]]:
    refresh, digest = TokenService.new_refresh_token()
    session_id = conn.execute(
        text("""
        INSERT INTO sessions (org_id, user_id, refresh_token_hash, family_id, expires_at, ip, user_agent)
        VALUES (:o, :u, :h, :f, :exp, CAST(:ip AS inet), :ua) RETURNING id"""),
        {
            "o": org_id,
            "u": user_id,
            "h": digest,
            "f": family_id,
            "exp": datetime.now(UTC) + state.tokens.refresh_ttl,
            "ip": _client_ip(request),
            "ua": (request.headers.get("user-agent") or "")[:300],
        },
    ).scalar_one()
    roles = conn.execute(text("SELECT role::text FROM user_roles WHERE user_id = :u"), {"u": user_id}).scalars().all()
    access = state.tokens.issue_access(AccessClaims(user_id, org_id, session_id, tuple(roles)))
    return access, f"{org_id}.{refresh}", list(roles)


def _set_cookies(response: Response, state: AppState, access: str, refresh: str) -> str:
    secure = state.settings.cookie_secure
    csrf = secrets.token_urlsafe(24)
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=int(state.tokens.access_ttl.total_seconds()),
        path="/api",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=int(state.tokens.refresh_ttl.total_seconds()),
        path="/api/v1/auth",
    )
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=secure, samesite="strict", path="/")
    return csrf


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, state: AppState = Depends(get_state)):
    with state.db.anonymous() as conn:
        account = conn.execute(text("SELECT * FROM urag_auth_lookup(:l)"), {"l": body.login}).first()
    now = datetime.now(UTC)
    if account is None:
        state.hasher.verify(None, body.password)  # même coût de calcul : pas d'oracle temporel
        raise problem(401, *INVALID)
    if account.locked_until is not None and account.locked_until > now:
        raise problem(423, "auth.locked", "Compte temporairement verrouillé, réessayez plus tard")
    ok = state.hasher.verify(account.password_hash, body.password) and account.status == "active"
    with state.db.org(account.org_id) as conn:
        if not ok:
            failures = account.failed_logins + 1
            limit = state.settings.login_max_failures
            locked = None
            if failures >= limit:
                locked = now + min(timedelta(hours=1), timedelta(minutes=2 ** (failures - limit)))
            conn.execute(
                text("UPDATE users SET failed_logins = :f, locked_until = :l WHERE id = :u"),
                {"f": failures, "l": locked, "u": account.user_id},
            )
            record(
                conn,
                account.org_id,
                "auth.login",
                actor=account.user_id,
                outcome="failure",
                ip=_client_ip(request),
                details={"failures": failures},
            )
        else:
            conn.execute(
                text("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = now() WHERE id = :u"),
                {"u": account.user_id},
            )
            access, refresh, roles = _open_session(conn, state, account.org_id, account.user_id, uuid.uuid4(), request)
            record(conn, account.org_id, "auth.login", actor=account.user_id, ip=_client_ip(request))
    if not ok:
        raise problem(401, *INVALID)
    csrf = _set_cookies(response, state, access, refresh)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "csrf_token": csrf,
        "token_type": "bearer",
        "user_id": str(account.user_id),
        "org_id": str(account.org_id),
        "roles": roles,
    }


class RefreshIn(BaseModel):
    refresh_token: str | None = None


@router.post("/refresh")
def refresh(request: Request, response: Response, body: RefreshIn | None = None, state: AppState = Depends(get_state)):
    raw = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE) or ""
    org_part, _, token = raw.partition(".")
    try:
        org_id = uuid.UUID(org_part)
    except ValueError:
        raise problem(401, "auth.invalid_token", "Session expirée ou invalide") from None
    with state.db.org(org_id) as conn:
        session = conn.execute(
            text("""
            SELECT s.id, s.user_id, s.family_id, s.revoked_at, s.expires_at, u.status::text AS status
            FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.refresh_token_hash = :h"""),
            {"h": hash_refresh_token(token)},
        ).first()
        if session is None:
            raise problem(401, "auth.invalid_token", "Session expirée ou invalide")
        if session.revoked_at is not None:
            # Réutilisation d'un jeton déjà échangé : vol probable, toute la famille est révoquée.
            conn.execute(
                text("UPDATE sessions SET revoked_at = now() WHERE family_id = :f AND revoked_at IS NULL"),
                {"f": session.family_id},
            )
            record(conn, org_id, "auth.refresh_reuse", actor=session.user_id, outcome="denied", ip=_client_ip(request))
            reused = True
        else:
            reused = False
            if session.expires_at <= datetime.now(UTC) or session.status != "active":
                raise problem(401, "auth.invalid_token", "Session expirée ou invalide")
            conn.execute(text("UPDATE sessions SET revoked_at = now() WHERE id = :s"), {"s": session.id})
            access, new_refresh, roles = _open_session(conn, state, org_id, session.user_id, session.family_id, request)
    if reused:
        raise problem(401, "auth.invalid_token", "Session expirée ou invalide")
    csrf = _set_cookies(response, state, access, new_refresh)
    return {"access_token": access, "refresh_token": new_refresh, "csrf_token": csrf, "roles": roles}


@router.post("/logout", status_code=204)
def logout(response: Response, user: CurrentUser = Depends(current_user), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        conn.execute(text("UPDATE sessions SET revoked_at = now() WHERE id = :s"), {"s": user.session_id})
        record(conn, user.org_id, "auth.logout", actor=user.user_id)
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name)


@router.get("/me")
def me(user: CurrentUser = Depends(current_user), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        row = conn.execute(
            text("""SELECT u.login, u.display_name, o.name AS org_name, u.status::text AS status
                                   FROM users u JOIN organizations o ON o.id = u.org_id WHERE u.id = :u"""),
            {"u": user.user_id},
        ).first()
        sess = conn.execute(text("SELECT revoked_at FROM sessions WHERE id = :s"), {"s": user.session_id}).first()
        mode = conn.execute(
            text("SELECT mode::text FROM ai_policies WHERE org_id = :o"), {"o": user.org_id}
        ).scalar_one_or_none()
    if row is None or row.status != "active" or sess is None or sess.revoked_at is not None:
        raise problem(401, "auth.invalid_token", "Session expirée ou invalide")
    return {
        "user_id": str(user.user_id),
        "login": row.login,
        "display_name": row.display_name,
        "organization": row.org_name,
        "roles": sorted(user.roles),
        "ai_mode": mode or "local_only",
    }
