"""Suite de conformité commune appliquée à la source simulée."""

from __future__ import annotations

import json

import pytest
from urag_connector_simulator import SimulatorConnector
from urag_connectors_base import ExternalPrincipalRef
from urag_connectors_base.conformance import ConformanceSuite, Harness


class SimHarness(Harness):
    def __init__(self, folder) -> None:
        self.path = folder / "coffre.json"
        self.vault = {
            "users": [{"id": "42", "name": "Alice", "login": "alice"}, {"id": "43", "name": "Bruno", "login": "bruno"}],
            "groups": [{"id": "7", "name": "Juridique", "members": ["42", "43"]}],
            "documents": [
                {
                    "id": n,
                    "version": 1,
                    "title": f"Document {n}",
                    "class": "Note",
                    "filename": f"{n}.txt",
                    "text": f"Document {n.upper()}, version 1.",
                    "acl": [{"group": "7"}],
                }
                for n in "abc"
            ],
            "journal": [{"seq": i + 1, "kind": "upsert", "id": n} for i, n in enumerate("abc")],
        }
        self._save()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.vault), encoding="utf-8")

    def _doc(self, name):
        return next(d for d in self.vault["documents"] if d["id"] == name)

    def _log(self, kind, name):
        self.vault["journal"].append({"seq": len(self.vault["journal"]) + 1, "kind": kind, "id": name})

    def connector(self):
        return SimulatorConnector({"path": str(self.path), "batch_size": 2})

    def external_id(self, name: str) -> str:
        return name

    def modify(self, name: str, text: str) -> None:
        d = self._doc(name)
        d["text"], d["version"] = text, d["version"] + 1
        self._log("upsert", name)
        self._save()

    def delete(self, name: str) -> None:
        self._doc(name)["deleted"] = True
        self._log("delete", name)
        self._save()

    def add(self, name: str, text: str) -> None:
        self.vault["documents"].append(
            {"id": name, "version": 1, "filename": f"{name}.txt", "text": text, "acl": [{"group": "7"}]}
        )
        self._log("upsert", name)
        self._save()

    def make_access_incomplete(self, name: str) -> bool:
        self._doc(name)["acl_complete"] = False
        self._save()
        return True

    def deny_user(self, name: str):
        self._doc(name)["acl"].append({"user": "43", "deny": True})
        self._save()
        return ExternalPrincipalRef("user", "43")


class TestConformiteSimulateur(ConformanceSuite):
    @pytest.fixture
    def harness(self, tmp_path):
        return SimHarness(tmp_path)


def test_droits_effectifs_par_groupe(tmp_path):
    h = SimHarness(tmp_path)
    with h.connector() as c:
        ref = next(d.ref for d in c.list_documents() if d.ref.external_id == "a")
        assert c.check_access(ExternalPrincipalRef("user", "42"), [ref]) == {ref: True}  # via le groupe 7
        assert c.check_access(ExternalPrincipalRef("user", "99"), [ref]) == {ref: False}  # inconnu : refusé
        snapshot = c.list_principals()
    assert (ExternalPrincipalRef("group", "7"), ExternalPrincipalRef("user", "42")) in snapshot.memberships
    assert snapshot.info[ExternalPrincipalRef("user", "42")].login == "alice"
