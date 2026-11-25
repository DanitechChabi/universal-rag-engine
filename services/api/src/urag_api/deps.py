"""Dépendances FastAPI : utilisateur courant, rôles, anti-CSRF."""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from urag_core.security import InvalidTokenError

from .state import AppState

ACCESS_COOKIE = "urag_access"
REFRESH_COOKIE = "urag_refresh"
CSRF_COOKIE = "urag_csrf"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def problem(status: int, code: str, title: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "title": title})


def get_state(request: Request) -> AppState:
    return request.app.state.urag


@dataclass(frozen=True)
class CurrentUser:
    user_id: uuid.UUID
    org_id: uuid.UUID
    session_id: uuid.UUID
    roles: frozenset[str]

    def has(self, *roles: str) -> bool:
        return bool(self.roles & set(roles)) or "super_admin" in self.roles


# Déclare le jeton porteur dans la description OpenAPI : bouton « Authorize » de la page /api/v1/docs.
bearer_scheme = HTTPBearer(auto_error=False, description="Jeton d'accès renvoyé par POST /auth/login")


def current_user(
    request: Request,
    state: AppState = Depends(get_state),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    token = credentials.credentials if credentials else None
    from_cookie = token is None
    if from_cookie:
        token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise problem(401, "auth.required", "Authentification requise")
    try:
        claims = state.tokens.verify_access(token)
    except InvalidTokenError as e:
        raise problem(401, "auth.invalid_token", "Session expirée ou invalide") from e
    if from_cookie and request.method in UNSAFE:
        sent = request.headers.get("x-csrf-token", "")
        expected = request.cookies.get(CSRF_COOKIE, "")
        if not expected or not hmac.compare_digest(sent, expected):
            raise problem(403, "auth.csrf", "Jeton anti-CSRF manquant ou invalide")
    # Révocation immédiate (docs/SECURITY.md §3) : session fermée, compte désactivé ou rôle retiré
    # s'appliquent à la requête suivante, sans attendre l'expiration du jeton (15 min).
    from sqlalchemy import text

    with state.db.org(claims.org_id) as conn:
        row = conn.execute(
            text("""
            SELECT u.status::text AS status, s.revoked_at,
                   coalesce(array_agg(r.role::text) FILTER (WHERE r.role IS NOT NULL), '{}') AS roles
            FROM users u
            JOIN sessions s ON s.id = :s AND s.user_id = u.id
            LEFT JOIN user_roles r ON r.user_id = u.id
            WHERE u.id = :u GROUP BY u.status, s.revoked_at"""),
            {"u": claims.user_id, "s": claims.session_id},
        ).first()
    if row is None or row.status != "active" or row.revoked_at is not None:
        raise problem(401, "auth.invalid_token", "Session expirée ou invalide")
    return CurrentUser(claims.user_id, claims.org_id, claims.session_id, frozenset(row.roles))


def require(*roles: str):
    def checker(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.has(*roles):
            raise problem(403, "auth.forbidden", "Droits insuffisants")
        return user

    return checker


ANY_USER = ("user", "doc_admin", "org_admin", "auditor")
CAN_ASK = ("user", "doc_admin", "org_admin")
DOC_ADMIN = ("doc_admin", "org_admin")
ORG_ADMIN = ("org_admin",)
