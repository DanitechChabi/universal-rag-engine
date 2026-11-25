"""Source simulée : un « coffre » décrit dans un fichier JSON (docs/CONNECTORS.md §4.5, étape 1).

Ce connecteur **ne simule pas M-Files** et ne suppose aucune de ses interfaces : il
respecte seulement le contrat commun des connecteurs, avec tout ce qu'une GED
apporte de difficile (droits par document, refus explicites, groupes, versions,
journal de changements, revérification des droits à la question). Il sert à
tester le cœur et la suite de conformité tant qu'aucun coffre réel n'est disponible.

Le fichier est relu à chaque appel : un test modifie le coffre en réécrivant le JSON.

Format ::

    {
      "users":  [{"id": "42", "name": "Alice", "login": "alice", "email": "alice@exemple.test"}],
      "groups": [{"id": "7", "name": "Juridique", "members": ["42"]}],
      "documents": [{
          "id": "101", "version": 1, "title": "Contrat de bail", "class": "Contrat",
          "filename": "bail.txt", "text": "…" | "file": "chemin/relatif.pdf",
          "acl": [{"user": "42"}, {"group": "7"}, {"user": "43", "deny": true}],
          "acl_complete": true, "deleted": false, "properties": {"Client": "SCI Les Pins"}
      }],
      "journal": [{"seq": 1, "kind": "upsert" | "delete" | "access_changed", "id": "101"}]
    }
"""

from __future__ import annotations

import json
import mimetypes
import shutil
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, ClassVar

from urag_connectors_base import (
    AccessEntry,
    BaseConnector,
    BrowseItem,
    Capabilities,
    Change,
    ChangeBatch,
    ConnectionReport,
    DocumentAccess,
    DocumentRef,
    ExternalPrincipalRef,
    FetchedFile,
    NotFoundError,
    PrincipalInfo,
    PrincipalSnapshot,
    SourceDocument,
    TransientError,
    UnsupportedError,
)


class SimulatorConnector(BaseConnector):
    kind: ClassVar[str] = "simulator"
    capabilities: ClassVar[Capabilities] = Capabilities(incremental=True, access=True, late_check=True, browse=True)

    def __init__(self, config, secrets=None) -> None:
        super().__init__(config, secrets)
        if not config.get("path"):
            raise UnsupportedError("chemin du coffre simulé requis (config.path)")
        self.path = Path(str(config["path"])).expanduser().resolve()
        self.batch_size = int(config.get("batch_size") or 100)
        self.link_template = config.get("link_template")  # ex. "https://ged.exemple.test/objets/{id}"

    # ------------------------------------------------------------ lecture du coffre

    def _vault(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise TransientError(f"coffre introuvable : {self.path}") from None

    def _docs(self, vault: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {str(d["id"]): d for d in vault.get("documents", [])}

    def _document(self, d: dict[str, Any]) -> SourceDocument:
        filename = d.get("filename") or (Path(d["file"]).name if d.get("file") else f"{d['id']}.txt")
        return SourceDocument(
            ref=DocumentRef(str(d["id"]), str(d.get("version", 1))),
            title=d.get("title") or Path(filename).stem,
            filename=filename,
            extension=Path(filename).suffix.lstrip(".").lower() or None,
            mime_type=mimetypes.guess_type(filename)[0],
            doc_class=d.get("class"),
            author=d.get("author"),
            location=d.get("class"),
            metadata={k: v for k, v in (d.get("properties") or {}).items()},
            source_metadata={"version": d.get("version", 1)},
        )

    # ------------------------------------------------------------ contrat

    def test_connection(self) -> ConnectionReport:
        if not self.path.is_file():
            return ConnectionReport(False, "coffre simulé introuvable")
        vault = self._vault()
        return ConnectionReport(True, f"{len(vault.get('documents', []))} document(s) dans le coffre simulé")

    def browse(self, container: str | None = None) -> list[BrowseItem]:
        classes = sorted({d.get("class") for d in self._vault().get("documents", []) if d.get("class")})
        return [BrowseItem(c, c, "document_class") for c in classes]

    def list_documents(self) -> Iterator[SourceDocument]:
        for d in self._vault().get("documents", []):
            if not d.get("deleted"):
                yield self._document(d)

    def list_changes(self, cursor) -> ChangeBatch:
        vault = self._vault()
        after = int((cursor or {}).get("seq", 0))
        pending = sorted((e for e in vault.get("journal", []) if int(e["seq"]) > after), key=lambda e: int(e["seq"]))
        batch, docs = pending[: self.batch_size], self._docs(vault)
        changes = []
        for e in batch:
            d = docs.get(str(e["id"]))
            if e["kind"] == "delete" or d is None or d.get("deleted"):
                changes.append(Change("delete", DocumentRef(str(e["id"]))))
            else:
                changes.append(Change(e["kind"], self._document(d).ref, self._document(d)))
        last = int(batch[-1]["seq"]) if batch else after
        return ChangeBatch(tuple(changes), {"seq": last}, complete=len(pending) <= self.batch_size)

    def fetch_content(self, ref: DocumentRef, dest_dir: Path) -> FetchedFile:
        vault = self._vault()
        d = self._docs(vault).get(ref.external_id)
        if d is None or d.get("deleted"):
            raise NotFoundError(ref.external_id)
        if ref.external_id in {str(x) for x in vault.get("transient_errors", [])}:
            raise TransientError(f"erreur simulée sur {ref.external_id}")
        doc = self._document(d)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"content{Path(doc.filename or '').suffix.lower() or '.txt'}"
        if d.get("file"):
            source = (self.path.parent / d["file"]).resolve()
            if not source.is_relative_to(self.path.parent):
                raise NotFoundError("fichier hors du dossier du coffre")
            shutil.copyfile(source, dest)
        else:
            dest.write_text(d.get("text", ""), encoding="utf-8")
        return FetchedFile(dest, doc.mime_type, dest.stat().st_size)

    def list_principals(self) -> PrincipalSnapshot:
        vault = self._vault()
        info: dict[ExternalPrincipalRef, PrincipalInfo] = {}
        for u in vault.get("users", []):
            info[ExternalPrincipalRef("user", str(u["id"]))] = PrincipalInfo(
                u.get("name"), u.get("login"), u.get("email")
            )
        for g in vault.get("groups", []):
            info[ExternalPrincipalRef("group", str(g["id"]))] = PrincipalInfo(g.get("name"))
        memberships = tuple(
            (ExternalPrincipalRef("group", str(g["id"])), ExternalPrincipalRef("user", str(m)))
            for g in vault.get("groups", [])
            for m in g.get("members", [])
        )
        return PrincipalSnapshot(tuple(info), memberships, info)

    @staticmethod
    def _principal(entry: dict[str, Any]) -> ExternalPrincipalRef:
        return (
            ExternalPrincipalRef("user", str(entry["user"]))
            if "user" in entry
            else ExternalPrincipalRef("group", str(entry["group"]))
        )

    def get_access(self, refs: Sequence[DocumentRef]) -> list[DocumentAccess]:
        docs = self._docs(self._vault())
        result = []
        for ref in refs:
            d = docs.get(ref.external_id)
            if d is None:
                result.append(DocumentAccess(ref, (), False, "document introuvable"))
                continue
            entries = tuple(AccessEntry(self._principal(e), not e.get("deny", False)) for e in d.get("acl", []))
            complete = bool(d.get("acl_complete", True))
            result.append(
                DocumentAccess(
                    ref, entries, complete, None if complete else "droits non résolus", {"acl": d.get("acl", [])}
                )
            )
        return result

    def check_access(self, principal: ExternalPrincipalRef, refs: Sequence[DocumentRef]) -> dict[DocumentRef, bool]:
        """Droits *effectifs* au moment de la question : un refus l'emporte toujours."""
        vault = self._vault()
        docs = self._docs(vault)
        groups = {
            ExternalPrincipalRef("group", str(g["id"]))
            for g in vault.get("groups", [])
            if principal.kind == "user" and principal.external_id in {str(m) for m in g.get("members", [])}
        }
        mine = {principal} | groups
        result = {}
        for ref in refs:
            d = docs.get(ref.external_id)
            if d is None or d.get("deleted") or not d.get("acl_complete", True):
                result[ref] = False
                continue
            entries = [(self._principal(e), not e.get("deny", False)) for e in d.get("acl", [])]
            if any(p in mine and not allow for p, allow in entries):
                result[ref] = False
            else:
                result[ref] = any(p in mine and allow for p, allow in entries)
        return result

    def external_link(self, ref: DocumentRef) -> str | None:
        return self.link_template.format(id=ref.external_id) if self.link_template else None


__all__ = ["SimulatorConnector"]
