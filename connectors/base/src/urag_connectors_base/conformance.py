"""Suite de conformité commune des connecteurs (docs/CONNECTORS.md §2.4).

Chaque connecteur fournit un *banc* (``Harness``) capable de créer une source de
test et de la modifier ; la même suite vérifie alors le contrat : idempotence de
la liste, lecture du contenu, modification et suppression détectées, droits
incomplets ⇒ ``complete=False``, curseur repris après interruption, refus
explicite prioritaire, fermeture propre.

Utilisation dans les tests d'un connecteur ::

    from urag_connectors_base.conformance import ConformanceSuite

    class TestConformite(ConformanceSuite):
        @pytest.fixture
        def harness(self, tmp_path):
            return MonBanc(tmp_path)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pytest

from . import (
    BaseConnector,
    DocumentRef,
    ExternalPrincipalRef,
    NotFoundError,
)


class Harness(ABC):
    """Source de test : trois documents au départ (``a``, ``b``, ``c``)."""

    @abstractmethod
    def connector(self) -> BaseConnector: ...

    @abstractmethod
    def external_id(self, name: str) -> str:
        """Identifiant externe du document logique ``name``."""

    @abstractmethod
    def modify(self, name: str, text: str) -> None: ...

    @abstractmethod
    def delete(self, name: str) -> None: ...

    @abstractmethod
    def add(self, name: str, text: str) -> None: ...

    def make_access_incomplete(self, name: str) -> bool:
        """Rend les droits d'un document impossibles à établir ; ``False`` si la source n'a pas de droits."""
        return False

    def deny_user(self, name: str) -> ExternalPrincipalRef | None:
        """Ajoute un refus explicite pour un utilisateur autorisé par ailleurs ; renvoie cet utilisateur."""
        return None


class ConformanceSuite:
    @pytest.fixture
    def harness(self) -> Harness:  # surchargé par chaque connecteur
        raise NotImplementedError

    @staticmethod
    def _listing(h: Harness) -> dict[str, str | None]:
        with h.connector() as c:
            return {d.ref.external_id: d.ref.version for d in c.list_documents()}

    def test_connexion(self, harness: Harness):
        with harness.connector() as c:
            assert c.test_connection().ok

    def test_liste_idempotente(self, harness: Harness):
        first, second = self._listing(harness), self._listing(harness)
        assert first == second
        assert {harness.external_id(n) for n in "abc"} <= set(first)

    def test_contenu_lisible(self, harness: Harness, tmp_path: Path):
        with harness.connector() as c:
            for doc in c.list_documents():
                fetched = c.fetch_content(doc.ref, tmp_path / doc.ref.external_id.replace("/", "_").replace("|", "_"))
                assert fetched.path.is_file() and fetched.size_bytes == fetched.path.stat().st_size > 0

    def test_document_inconnu(self, harness: Harness, tmp_path: Path):
        with harness.connector() as c, pytest.raises(NotFoundError):
            c.fetch_content(DocumentRef(harness.external_id("inexistant")), tmp_path)

    def test_modification_change_la_version(self, harness: Harness):
        before = self._listing(harness)
        harness.modify("a", "Nouveau texte du document A, version 2.")
        after = self._listing(harness)
        ida = harness.external_id("a")
        assert after[ida] != before[ida]
        assert {k: v for k, v in after.items() if k != ida} == {k: v for k, v in before.items() if k != ida}

    def test_suppression_detectee(self, harness: Harness, tmp_path: Path):
        harness.delete("b")
        idb = harness.external_id("b")
        assert idb not in self._listing(harness)
        with harness.connector() as c, pytest.raises(NotFoundError):
            c.fetch_content(DocumentRef(idb), tmp_path)

    def test_un_droit_par_document(self, harness: Harness):
        with harness.connector() as c:
            refs = [d.ref for d in c.list_documents()]
            accesses = c.get_access(refs)
        assert [a.ref.external_id for a in accesses] == [r.external_id for r in refs]
        for a in accesses:
            assert a.complete or a.reason, "droits incomplets sans raison"

    def test_droits_incomplets_signales(self, harness: Harness):
        if not harness.make_access_incomplete("c"):
            pytest.skip("la source ne fournit pas de droits par document")
        idc = harness.external_id("c")
        with harness.connector() as c:
            access = next(a for a in c.get_access([d.ref for d in c.list_documents()]) if a.ref.external_id == idc)
        assert access.complete is False and access.reason

    def test_curseur_repris_apres_interruption(self, harness: Harness):
        with harness.connector() as c:
            if not c.capabilities.incremental:
                pytest.skip("pas de synchronisation incrémentale")
            initial = c.list_changes(None)
            cursor = initial.cursor
            while not initial.complete:  # rattraper l'état initial
                initial = c.list_changes(cursor)
                cursor = initial.cursor
        for i in range(5):
            harness.add(f"n{i}", f"Nouveau document numéro {i}.")
        seen: list[str] = []
        with harness.connector() as c:
            first = c.list_changes(cursor)  # un lot traité, puis « interruption »
            seen += [ch.ref.external_id for ch in first.changes]
        with harness.connector() as c:  # reprise avec le curseur enregistré après le lot
            cursor = first.cursor
            batch = first
            while not batch.complete:
                batch = c.list_changes(cursor)
                seen += [ch.ref.external_id for ch in batch.changes]
                cursor = batch.cursor
        assert sorted(seen) == sorted(harness.external_id(f"n{i}") for i in range(5)), "doublon ou perte"

    def test_refus_explicite_prioritaire(self, harness: Harness):
        user = harness.deny_user("a")
        if user is None:
            pytest.skip("la source ne gère pas de refus explicite")
        ref = DocumentRef(harness.external_id("a"))
        with harness.connector() as c:
            access = next(x for x in c.get_access([ref]))
            assert any(not e.allow for e in access.entries)
            if c.capabilities.late_check:
                assert c.check_access(user, [ref]) == {ref: False}

    def test_fermeture_propre(self, harness: Harness):
        c = harness.connector()
        c.open()
        c.close()
        c.close()  # deux fermetures sans erreur
