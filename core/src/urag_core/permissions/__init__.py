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
    deny: tuple[str, ...] = ()  # refus explicites (ADR-0020)


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
    deny: set[str] = set()
    for entry in access.entries:
        if entry.principal == "space":
            if not entry.allow:
                return DocumentKeys((), False, "refus visant tout l'espace")
            if inherit_space_access:
                keys.add(f"sp:{space_id}")
            continue
        internal = external_ids.get(entry.principal)
        if internal is None:
            # Un refus mal résolu pourrait laisser passer la personne visée : document invisible.
            return DocumentKeys((), False, f"identité externe inconnue : {entry.principal.external_id}")
        prefix = "xu" if entry.principal.kind == "user" else "xg"
        (keys if entry.allow else deny).add(f"{prefix}:{internal}")
    return DocumentKeys(tuple(sorted(keys)), True, None, tuple(sorted(deny)))


def late_check(conn: Connection, scope: AccessScope, document_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Revérifie auprès de la source les droits *effectifs* de l'utilisateur (docs/CONNECTORS.md §4.3).

    Ne concerne que les sources capables de le faire (``capabilities.late_check``) ; pour
    les autres, les clés d'accès suffisent. Renvoie les documents autorisés. Fermé par
    défaut : sans identité confirmée dans la source, ou si la source ne répond pas, ses
    documents sont écartés. Les clés restent un pré-filtre : ceci ne peut qu'exclure.
    """
    from urag_connectors_base import ConnectorError, DocumentRef, load_connector_class

    if not document_ids:
        return set()
    rows = conn.execute(
        text("""
        SELECT d.id, d.external_id, d.source_version, s.id AS source_id, s.kind::text AS kind, s.config
        FROM documents d JOIN sources s ON s.id = d.source_id
        WHERE d.id = ANY(CAST(:ids AS uuid[]))"""),
        {"ids": [str(i) for i in document_ids]},
    ).all()
    allowed: set[uuid.UUID] = set()
    by_source: dict[uuid.UUID, list] = {}
    for r in rows:
        by_source.setdefault(r.source_id, []).append(r)
    denied = 0
    for source_id, docs in by_source.items():
        try:
            cls = load_connector_class(docs[0].kind)
        except Exception:  # noqa: BLE001 - connecteur absent : on s'en tient aux clés
            allowed |= {d.id for d in docs}
            continue
        if not cls.capabilities.late_check:
            allowed |= {d.id for d in docs}
            continue
        principal = conn.execute(
            text("""
            SELECT ep.external_id FROM principal_links pl
            JOIN external_principals ep ON ep.id = pl.external_principal_id
            WHERE pl.user_id = :u AND pl.verified AND ep.source_id = :s AND ep.kind = 'user'"""),
            {"u": scope.user_id, "s": source_id},
        ).scalar()
        if principal is None:
            denied += len(docs)
            continue
        refs = {DocumentRef(d.external_id, d.source_version): d.id for d in docs}
        try:
            with cls(dict(docs[0].config)) as connector:
                verdict = connector.check_access(ExternalPrincipalRef("user", principal), list(refs))
        except ConnectorError:
            denied += len(docs)  # source injoignable : rien n'est montré
            continue
        for ref, doc_id in refs.items():
            if verdict.get(ref) is True:
                allowed.add(doc_id)
            else:
                denied += 1
    if denied:
        from ..audit import record

        record(conn, scope.org_id, "access.late_denied", actor=scope.user_id, details={"documents": denied})
    return allowed
