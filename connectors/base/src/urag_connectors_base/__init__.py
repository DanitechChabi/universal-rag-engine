"""Interface commune des connecteurs documentaires (docs/CONNECTORS.md §2).

Un connecteur sait parler à une source : se connecter, lister, lire le contenu,
lire les droits, détecter les changements. Il ne sait rien de la RAG.
Ce paquet n'a aucune dépendance : le cœur et les connecteurs en dépendent.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

JsonValue = Any

# --------------------------------------------------------------------- erreurs


class ConnectorError(Exception):
    """Erreur générique : le document concerné passe en échec, sans bloquer les autres."""


class AuthenticationError(ConnectorError):
    """Identifiants refusés : source en erreur, pas de nouvelle tentative automatique."""


class TransientError(ConnectorError):
    """Réseau, délai, serveur occupé : nouvelle tentative avec attente croissante."""


class NotFoundError(ConnectorError):
    """Document disparu entre la liste et la lecture : traité comme une suppression."""


class AccessDeniedError(ConnectorError):
    """Le compte technique ne peut pas lire l'objet : document exclu."""


class UnsupportedError(ConnectorError):
    """Format ou fonction non pris en charge : document exclu."""


# ----------------------------------------------------------------------- types


@dataclass(frozen=True)
class DocumentRef:
    external_id: str
    version: str | None = None


@dataclass(frozen=True)
class SourceDocument:
    ref: DocumentRef
    title: str
    filename: str | None = None
    extension: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    author: str | None = None
    doc_class: str | None = None
    location: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    source_metadata: dict[str, JsonValue] = field(default_factory=dict)
    content_hash: str | None = None


@dataclass(frozen=True)
class ExternalPrincipalRef:
    kind: Literal["user", "group"]
    external_id: str


@dataclass(frozen=True)
class AccessEntry:
    """Une entrée de droit. ``principal == "space"`` : tous les membres de l'espace."""

    principal: ExternalPrincipalRef | Literal["space"]
    allow: bool = True


@dataclass(frozen=True)
class DocumentAccess:
    ref: DocumentRef
    entries: tuple[AccessEntry, ...]
    complete: bool
    reason: str | None = None
    raw: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class Change:
    kind: Literal["upsert", "delete", "access_changed"]
    ref: DocumentRef
    document: SourceDocument | None = None


@dataclass(frozen=True)
class ChangeBatch:
    changes: tuple[Change, ...]
    cursor: dict[str, JsonValue]
    complete: bool = True  # False : d'autres lots suivent


@dataclass(frozen=True)
class FetchedFile:
    path: Path
    mime_type: str | None
    size_bytes: int


@dataclass(frozen=True)
class ConnectionReport:
    ok: bool
    message: str
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowseItem:
    id: str
    name: str
    kind: Literal["container", "document_class", "document"]


@dataclass(frozen=True)
class PrincipalSnapshot:
    principals: tuple[ExternalPrincipalRef, ...] = ()
    memberships: tuple[tuple[ExternalPrincipalRef, ExternalPrincipalRef], ...] = ()  # (groupe, utilisateur)


@dataclass(frozen=True)
class Capabilities:
    incremental: bool = False
    access: bool = False  # la source fournit des droits par document
    late_check: bool = False  # revérification des droits d'un utilisateur à la question
    browse: bool = False


# ------------------------------------------------------------------ interface


@runtime_checkable
class Connector(Protocol):
    kind: ClassVar[str]
    capabilities: ClassVar[Capabilities]

    def open(self) -> None: ...
    def close(self) -> None: ...
    def test_connection(self) -> ConnectionReport: ...
    def browse(self, container: str | None = None) -> list[BrowseItem]: ...
    def list_documents(self) -> Iterator[SourceDocument]: ...
    def list_changes(self, cursor: dict[str, JsonValue] | None) -> ChangeBatch: ...
    def fetch_content(self, ref: DocumentRef, dest_dir: Path) -> FetchedFile: ...
    def list_principals(self) -> PrincipalSnapshot: ...
    def get_access(self, refs: Sequence[DocumentRef]) -> list[DocumentAccess]: ...
    def check_access(self, principal: ExternalPrincipalRef, refs: Sequence[DocumentRef]) -> dict[DocumentRef, bool]: ...


class BaseConnector:
    """Implémentations par défaut prudentes (aucun droit fourni ⇒ droits incomplets)."""

    kind: ClassVar[str] = "base"
    capabilities: ClassVar[Capabilities] = Capabilities()

    def __init__(self, config: dict[str, JsonValue], secrets: dict[str, str] | None = None) -> None:
        self.config = config
        self.secrets = secrets or {}

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def __enter__(self) -> BaseConnector:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def browse(self, container: str | None = None) -> list[BrowseItem]:
        raise UnsupportedError("exploration non prise en charge")

    def list_principals(self) -> PrincipalSnapshot:
        return PrincipalSnapshot()

    def get_access(self, refs: Sequence[DocumentRef]) -> list[DocumentAccess]:
        return [
            DocumentAccess(ref=r, entries=(), complete=False, reason="droits non fournis par la source") for r in refs
        ]

    def check_access(self, principal: ExternalPrincipalRef, refs: Sequence[DocumentRef]) -> dict[DocumentRef, bool]:
        raise UnsupportedError("revérification des droits non prise en charge")

    def external_link(self, ref: DocumentRef) -> str | None:
        """Lien d'ouverture dans l'application de la source (ex. client de GED), sinon ``None`` :
        le fichier est alors servi par l'API."""
        return None


def load_connector_class(kind: str) -> type[BaseConnector]:
    """Registre : les connecteurs sont découverts par points d'entrée ``urag.connectors``."""
    for ep in entry_points(group="urag.connectors"):
        if ep.name == kind:
            cls = ep.load()
            if not isinstance(cls, type):
                raise ConnectorError(f"point d'entrée invalide pour {kind}")
            return cls
    raise UnsupportedError(f"aucun connecteur installé pour « {kind} »")


__all__ = [
    "AccessDeniedError",
    "AccessEntry",
    "AuthenticationError",
    "BaseConnector",
    "BrowseItem",
    "Capabilities",
    "Change",
    "ChangeBatch",
    "ConnectionReport",
    "Connector",
    "ConnectorError",
    "DocumentAccess",
    "DocumentRef",
    "ExternalPrincipalRef",
    "FetchedFile",
    "NotFoundError",
    "PrincipalSnapshot",
    "SourceDocument",
    "TransientError",
    "UnsupportedError",
    "load_connector_class",
]
