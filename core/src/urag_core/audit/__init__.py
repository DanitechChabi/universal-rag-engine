"""Journal d'audit en ajout seul (docs/SECURITY.md §7). Jamais de contenu documentaire ni de secret."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import Connection, text

FORBIDDEN_KEYS = {"password", "api_key", "token", "secret", "credentials", "answer", "excerpt", "content"}


def record(conn: Connection, org_id: uuid.UUID, action: str, *, actor: uuid.UUID | None = None,
           outcome: str = "success", target_type: str | None = None, target_id: str | None = None,
           ip: str | None = None, details: dict[str, Any] | None = None) -> None:
    details = details or {}
    leaked = FORBIDDEN_KEYS & {k.lower() for k in details}
    if leaked:
        raise ValueError(f"champ interdit dans l'audit : {sorted(leaked)}")
    conn.execute(text("""
        INSERT INTO audit_log (org_id, actor_user_id, action, outcome, target_type, target_id, ip, details)
        VALUES (:o, :a, :ac, :oc, :tt, :ti, CAST(:ip AS inet), CAST(:d AS jsonb))"""),
        {"o": org_id, "a": actor, "ac": action, "oc": outcome, "tt": target_type, "ti": target_id,
         "ip": ip, "d": json.dumps(details, default=str)})
