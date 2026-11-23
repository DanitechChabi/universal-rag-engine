"""Connecteur de fichiers locaux (docs/CONNECTORS.md §3).

Configuration (non secrète) :
    roots              liste de dossiers (locaux, partages réseau, montages)
    include_extensions extensions acceptées (défaut : formats prioritaires)
    exclude_globs      motifs de chemins relatifs à exclure (ex. "archives/**")
    max_size_bytes     taille maximale (défaut 200 Mo)

Pas de droits propres : chaque document reçoit l'entrée « space ». Le cœur la
traduit en clé ``sp:<espace>`` seulement si la source est configurée pour hériter
de l'espace ; sinon le document n'est visible par personne (fermé par défaut).
"""

from __future__ import annotations

import fnmatch
import mimetypes
import os
import shutil
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from urag_connectors_base import (
    AccessDeniedError,
    AccessEntry,
    BaseConnector,
    Capabilities,
    ChangeBatch,
    ConnectionReport,
    DocumentAccess,
    DocumentRef,
    FetchedFile,
    NotFoundError,
    SourceDocument,
    UnsupportedError,
)

DEFAULT_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".txt",
    ".csv",
    ".rtf",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".md",
)
IGNORED_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
IGNORED_PREFIXES = ("~$", ".~lock.", "._")
IGNORED_SUFFIXES = (".tmp", ".temp", ".swp", ".part", ".crdownload")
IGNORED_DIRS = {"$recycle.bin", "system volume information", "__pycache__", ".git"}
SEPARATOR = "|"


def is_ignored_name(name: str) -> bool:
    low = name.lower()
    return (
        low in IGNORED_NAMES
        or low.startswith(".")
        or any(low.startswith(p) for p in IGNORED_PREFIXES)
        or any(low.endswith(s) for s in IGNORED_SUFFIXES)
    )


class LocalFilesConnector(BaseConnector):
    kind: ClassVar[str] = "local_files"
    capabilities: ClassVar[Capabilities] = Capabilities(incremental=False, access=True, browse=True)

    def __init__(self, config, secrets=None) -> None:
        super().__init__(config, secrets)
        roots = config.get("roots") or []
        if not roots:
            raise UnsupportedError("au moins un dossier racine est requis")
        self.roots = [Path(r).expanduser().resolve() for r in roots]
        self.extensions = tuple(e.lower() for e in config.get("include_extensions") or DEFAULT_EXTENSIONS)
        self.exclude_globs = tuple(config.get("exclude_globs") or ())
        self.max_size = int(config.get("max_size_bytes") or 200 * 1024 * 1024)

    # ------------------------------------------------------------ identité

    def _external_id(self, root: Path, path: Path) -> str:
        return f"{root.as_posix()}{SEPARATOR}{path.relative_to(root).as_posix()}"

    def _resolve(self, external_id: str) -> Path:
        root_str, _, rel = external_id.partition(SEPARATOR)
        root = Path(root_str)
        if root not in self.roots:
            raise NotFoundError(f"racine inconnue : {root_str}")
        path = (root / rel).resolve()
        if not path.is_relative_to(root):  # jamais en dehors de la racine
            raise AccessDeniedError("chemin hors de la racine")
        return path

    # ------------------------------------------------------------ opérations

    def test_connection(self) -> ConnectionReport:
        missing = [str(r) for r in self.roots if not r.is_dir()]
        unreadable = [str(r) for r in self.roots if r.is_dir() and not os.access(r, os.R_OK | os.X_OK)]
        if missing or unreadable:
            return ConnectionReport(
                False, "dossier introuvable ou illisible", {"missing": missing, "unreadable": unreadable}
            )
        return ConnectionReport(True, f"{len(self.roots)} dossier(s) accessible(s)")

    def _excluded(self, rel: str) -> bool:
        return any(fnmatch.fnmatch(rel, g) for g in self.exclude_globs)

    def _walk(self) -> Iterator[tuple[Path, Path]]:
        for root in self.roots:
            if not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                current = Path(dirpath)
                dirnames[:] = sorted(
                    d
                    for d in dirnames
                    if d.lower() not in IGNORED_DIRS
                    and not d.startswith(".")
                    and not self._excluded((current / d).relative_to(root).as_posix() + "/")
                )
                for name in sorted(filenames):
                    path = current / name
                    if is_ignored_name(name) or path.is_symlink():
                        continue
                    if path.suffix.lower() not in self.extensions:
                        continue
                    if self._excluded(path.relative_to(root).as_posix()):
                        continue
                    yield root, path

    def list_documents(self) -> Iterator[SourceDocument]:
        for root, path in self._walk():
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_size > self.max_size or st.st_size == 0:
                continue
            modified = datetime.fromtimestamp(st.st_mtime, tz=UTC)
            ext = path.suffix.lower()
            yield SourceDocument(
                ref=DocumentRef(self._external_id(root, path), version=f"{st.st_size}:{st.st_mtime_ns}"),
                title=path.stem,
                filename=path.name,
                extension=ext.lstrip("."),
                mime_type=mimetypes.guess_type(path.name)[0],
                size_bytes=st.st_size,
                modified_at=modified,
                location=path.relative_to(root).parent.as_posix(),
            )

    def list_changes(self, cursor) -> ChangeBatch:
        raise UnsupportedError("synchronisation par comparaison complète (pas de curseur)")

    def fetch_content(self, ref: DocumentRef, dest_dir: Path) -> FetchedFile:
        path = self._resolve(ref.external_id)
        if not path.is_file():
            raise NotFoundError(ref.external_id)
        if not os.access(path, os.R_OK):
            raise AccessDeniedError(ref.external_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"content{path.suffix.lower()}"
        shutil.copyfile(path, dest)
        return FetchedFile(dest, mimetypes.guess_type(path.name)[0], dest.stat().st_size)

    def get_access(self, refs: Sequence[DocumentRef]) -> list[DocumentAccess]:
        return [DocumentAccess(ref=r, entries=(AccessEntry("space"),), complete=True) for r in refs]


__all__ = ["LocalFilesConnector", "is_ignored_name"]
