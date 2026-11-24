"""Schéma initial (figé) : copie du schéma de référence de la phase 1 dans migrations/sql/.

Revision ID: 0001
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[1] / "sql"  # copies figées : ne jamais les modifier


def _statements(path: Path) -> str:
    sql = path.read_text(encoding="utf-8")
    # La migration s'exécute déjà dans une transaction Alembic.
    lines = [ln for ln in sql.splitlines() if ln.strip().upper() not in ("BEGIN;", "COMMIT;")]
    return "\n".join(lines)


def upgrade() -> None:
    op.execute(_statements(SQL / "0001_roles.sql"))
    op.execute(_statements(SQL / "0001_schema.sql"))


def downgrade() -> None:
    raise NotImplementedError("pas de retour arrière du schéma initial : restaurer une sauvegarde")
