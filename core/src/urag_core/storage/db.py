"""PostgreSQL : l'organisation courante est fixée au début de chaque transaction.

Sans organisation (``Database.anonymous``), la RLS ne laisse rien voir : seule
la fonction ``urag_auth_lookup`` est utilisable (connexion).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, create_engine, text


class Database:
    def __init__(self, url: str, pool_size: int = 10) -> None:
        self.engine = create_engine(url, pool_pre_ping=True, pool_size=pool_size, max_overflow=5)

    @contextmanager
    def org(self, org_id: uuid.UUID) -> Iterator[Connection]:
        """Transaction limitée à une organisation (SET LOCAL urag.org_id)."""
        if not isinstance(org_id, uuid.UUID):
            raise TypeError("org_id doit être un UUID")
        with self.engine.begin() as conn:
            conn.execute(text("SELECT set_config('urag.org_id', :o, true)"), {"o": str(org_id)})
            yield conn

    @contextmanager
    def anonymous(self) -> Iterator[Connection]:
        with self.engine.begin() as conn:
            conn.execute(text("SELECT set_config('urag.org_id', '', true)"))
            yield conn

    def dispose(self) -> None:
        self.engine.dispose()
