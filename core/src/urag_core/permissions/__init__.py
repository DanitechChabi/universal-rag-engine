"""Clés d'accès (docs/SECURITY.md §2, ADR-0006).

Une clé est une chaîne ``u:``, ``g:``, ``sp:``, ``xu:`` ou ``xg:`` suivie d'un UUID.
Un passage est visible si au moins une clé est commune entre le document et
l'utilisateur, et si les droits du document sont complets.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text
from urag_connectors_base import DocumentAccess, ExternalPrincipalRef


@dataclass(frozen=True)
class AccessScope:
    org_id: uuid.UUID
    user_id: uuid.UUID
    keys: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        """Empreinte des droits : sert de composante de clé de cache (jamais de cache partagé)."""
        return hashlib.sha256("|".join(sorted(self.keys)).encode()).hexdigest()[:16]

    @classmethod
    def for_user(cls, conn: Connection, org_id: uuid.UUID, user_id: uuid.UUID) -> AccessScope:
        """Recalculé à chaque question : une révocation prend effet immédiatement."""
        keys = conn.execute(text("SELECT urag_user_access_keys(:u)"), {"u": user_id}).scalar_one()
        return cls(org_id, user_id, tuple(sorted(keys or ())))


@dataclass(frozen=True)
class DocumentKeys:
    keys: tuple[str, ...]
    complete: bool
    reason: str | None


def document_keys(
    access: DocumentAccess,
    space_id: uuid.UUID,
    inherit_space_access: bool,
    external_ids: dict[ExternalPrincipalRef, uuid.UUID],
) -> DocumentKeys:
    """Traduit les droits de la source en clés. Tout doute ⇒ aucune clé."""
    if not access.complete:
        return DocumentKeys((), False, access.reason or "droits incomplets")
    keys: set[str] = set()
    for entry in access.entries:
        if not entry.allow:
            # Un refus explicite ne peut pas être représenté par des clés positives.
            return DocumentKeys((), False, "refus explicite non représentable")
        if entry.principal == "space":
            if inherit_space_access:
                keys.add(f"sp:{space_id}")
            continue
        internal = external_ids.get(entry.principal)
        if internal is None:
            return DocumentKeys((), False, f"identité externe inconnue : {entry.principal.external_id}")
        prefix = "xu" if entry.principal.kind == "user" else "xg"
        keys.add(f"{prefix}:{internal}")
    return DocumentKeys(tuple(sorted(keys)), True, None)
