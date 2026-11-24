"""Environnement Alembic. URL d'administration (propriétaire du schéma) : URAG_ADMIN_DATABASE_URL."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

url = context.config.get_main_option("sqlalchemy.url") or os.environ["URAG_ADMIN_DATABASE_URL"]


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
