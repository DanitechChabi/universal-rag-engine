"""Les migrations Alembic produisent exactement le schéma de référence (database/schemas/schema.sql)."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.integration.conftest import ADMIN_URL, _reachable

pytestmark = pytest.mark.integration
SCHEMAS = Path(__file__).resolve().parents[2] / "database" / "schemas"


def _dump(url) -> str:
    out = subprocess.run(
        [
            "pg_dump",
            "-s",
            "--no-owner",
            "--no-privileges",
            "-T",
            "alembic_version",
            "-h",
            url.host,
            "-U",
            url.username,
            "-d",
            url.database,
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"PGPASSWORD": url.password or "", "PATH": "/usr/bin"},
    ).stdout
    return "\n".join(
        line
        for line in out.splitlines()
        if line.strip() and not line.startswith(("--", "\\restrict", "\\unrestrict", "SET ", "SELECT pg_catalog"))
    )


def test_migrations_identiques_au_schema_de_reference():
    reason = _reachable()
    if reason:
        pytest.skip(reason)
    from urag_api import cli

    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    names = [f"urag_mig_{uuid.uuid4().hex[:6]}", f"urag_ref_{uuid.uuid4().hex[:6]}"]
    with admin.connect() as c:
        for n in names:
            c.execute(text(f'CREATE DATABASE "{n}"'))
    try:
        mig, ref = (make_url(ADMIN_URL).set(database=n) for n in names)
        cli.main(["--admin-url", mig.render_as_string(hide_password=False), "migrate"])
        for f in ("roles.sql", "schema.sql"):  # appliqué tel quel par psql, comme test_schema.sh
            subprocess.run(
                [
                    "psql",
                    "-X",
                    "-q",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-h",
                    ref.host,
                    "-U",
                    ref.username,
                    "-d",
                    ref.database,
                    "-f",
                    str(SCHEMAS / f),
                ],
                check=True,
                capture_output=True,
                env={"PGPASSWORD": ref.password or "", "PATH": "/usr/bin"},
            )
        mig_dump, ref_dump = _dump(mig), _dump(ref)
        assert len(ref_dump) > 10_000 and "searchable_chunks" in ref_dump  # comparaison non vide
        assert mig_dump == ref_dump
    finally:
        with admin.connect() as c:
            for n in names:
                c.execute(text(f'DROP DATABASE IF EXISTS "{n}" WITH (FORCE)'))
