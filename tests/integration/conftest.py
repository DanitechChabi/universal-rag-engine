"""Pile réelle pour les tests d'intégration : PostgreSQL (base neuve migrée), Qdrant, Ollama.

Variables (valeurs par défaut = environnement de développement, docs/DEVELOPMENT.md) :
    URAG_TEST_ADMIN_URL   superutilisateur PostgreSQL
    URAG_TEST_QDRANT_URL / URAG_TEST_QDRANT_KEY
    URAG_TEST_OLLAMA_URL
"""

from __future__ import annotations

import os
import secrets
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ADMIN_URL = os.environ.get("URAG_TEST_ADMIN_URL", "postgresql+psycopg://postgres:postgres-dev@127.0.0.1:5432/postgres")
QDRANT_URL = os.environ.get("URAG_TEST_QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_KEY = os.environ.get("URAG_TEST_QDRANT_KEY", "dev-qdrant-key")
OLLAMA_URL = os.environ.get("URAG_TEST_OLLAMA_URL", "http://127.0.0.1:11434")
APP_PASSWORD = "app-" + secrets.token_hex(8)
APP_ROLE = f"urag_run_{secrets.token_hex(6)}"  # compte propre à cette exécution (voir cli.create_run_role)


def _reachable() -> str | None:
    try:
        with create_engine(ADMIN_URL).connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        return f"PostgreSQL indisponible : {e}"
    try:
        httpx.get(QDRANT_URL, headers={"api-key": QDRANT_KEY}, timeout=3).raise_for_status()
    except Exception as e:  # noqa: BLE001
        return f"Qdrant indisponible : {e}"
    return None


@pytest.fixture(scope="session")
def database():
    reason = _reachable()
    if reason:
        pytest.skip(reason)
    from urag_api import cli
    from urag_api.cli import DATABASE_DIR  # noqa: F401 - vérifie l'emplacement des migrations

    name = f"urag_it_{uuid.uuid4().hex[:8]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    admin_db_url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    cli.main(["--admin-url", admin_db_url, "migrate"])
    cli.create_run_role(admin_db_url, APP_ROLE, APP_PASSWORD)
    app_url = make_url(admin_db_url).set(username=APP_ROLE, password=APP_PASSWORD).render_as_string(hide_password=False)
    yield {"admin_url": admin_db_url, "app_url": app_url}
    with admin.connect() as c:
        c.execute(text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{name}'"))
        c.execute(text(f'DROP DATABASE "{name}"'))
    cli.drop_run_role(ADMIN_URL, APP_ROLE)


def make_state(database, tmp_path, encoder, router):
    from urag_api.state import AppState
    from urag_core.config import Settings
    from urag_core.security import SecretBox, TokenService
    from urag_core.storage import Database, VectorStore

    settings = Settings(
        database_url=database["app_url"],
        qdrant_url=QDRANT_URL,
        ollama_url=OLLAMA_URL,
        cookie_secure=False,
        tmp_dir=tmp_path / "work",
        context_passages=6,
    )
    tokens = TokenService(secrets.token_bytes(32), timedelta(minutes=15), timedelta(hours=12))
    return AppState(
        settings,
        Database(database["app_url"]),
        VectorStore(QDRANT_URL, QDRANT_KEY),
        tokens,
        encoder_override=encoder,
        router_override=router,
        secrets=SecretBox(secrets.token_bytes(32)),
    )


def login(client, login_name: str, password: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"login": login_name, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def sse_events(body: str) -> list[tuple[str, dict]]:
    import json

    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events
