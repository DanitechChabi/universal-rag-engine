"""Suite de conformité commune appliquée au connecteur fichiers locaux."""

from __future__ import annotations

import os

import pytest
from urag_connector_local_files import LocalFilesConnector
from urag_connectors_base.conformance import ConformanceSuite, Harness


class LocalHarness(Harness):
    def __init__(self, root) -> None:
        self.root = root
        for n in "abc":
            (root / f"{n}.txt").write_text(f"Document {n.upper()}, version 1.", encoding="utf-8")

    def connector(self):
        return LocalFilesConnector({"roots": [str(self.root)]})

    def external_id(self, name: str) -> str:
        return f"{self.root.resolve().as_posix()}|{name}.txt"

    def modify(self, name: str, text: str) -> None:
        path = self.root / f"{name}.txt"
        st = path.stat()
        path.write_text(text, encoding="utf-8")
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))  # horloge grossière de certains systèmes

    def delete(self, name: str) -> None:
        (self.root / f"{name}.txt").unlink()

    def add(self, name: str, text: str) -> None:
        (self.root / f"{name}.txt").write_text(text, encoding="utf-8")


class TestConformiteFichiersLocaux(ConformanceSuite):
    @pytest.fixture
    def harness(self, tmp_path):
        return LocalHarness(tmp_path)
