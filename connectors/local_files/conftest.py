import tempfile

import pytest


@pytest.fixture(autouse=True)
def _racines_autorisees(monkeypatch):
    """Tests du connecteur : dossiers temporaires autorisés, comme le ferait l'installation."""
    monkeypatch.setenv("URAG_LOCAL_FILES_ALLOWED_ROOTS", tempfile.gettempdir())
