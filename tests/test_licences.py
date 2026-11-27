"""Classement des licences par tools/verifier_licences.py (règle : aucune AGPL/SSPL livrée)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "verifier_licences", Path(__file__).resolve().parents[1] / "tools" / "verifier_licences.py"
)
licences = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(licences)


@pytest.mark.parametrize(
    ("texte", "classe"),
    [
        ("MIT", "permissive"),
        ("Apache-2.0 OR BSD-3-Clause", "permissive"),
        ("BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0", "permissive"),
        ("PSF-2.0", "permissive"),
        ("LGPL-3.0-only", "copyleft faible"),
        ("GNU Lesser General Public License v3 (LGPLv3)", "copyleft faible"),
        ("Mozilla Public License 2.0 (MPL 2.0)", "copyleft faible"),
        ("AGPL-3.0-or-later", "refusée"),
        ("GNU Affero General Public License v3", "refusée"),
        ("SSPL-1.0", "refusée"),
        ("GPL-3.0-only", "refusée"),
        ("GNU General Public License v2 (GPLv2)", "refusée"),
        ("LGPL-2.1 OR GPL-3.0", "refusée"),  # le choix GPL ne doit pas passer inaperçu
        ("BUSL-1.1", "refusée"),
        ("RSALv2", "refusée"),
        ("CC-BY-NC-4.0", "refusée"),
        ("MIT with Commons Clause", "refusée"),
        ("Proprietary", "inconnue"),
        ("", "inconnue"),
    ],
)
def test_classement(texte, classe):
    assert licences.classify(texte) == classe
