"""Schéma initial : reproduit exactement database/schemas/schema.sql (testé par test_schema.sh).

Revision ID: 0001
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def _statements(path: Path) -> str:
    sql = path.read_text(encoding="utf-8")
    # La migration s'exécute déjà dans une transaction Alembic.
    lines = [ln for ln in sql.splitlines() if ln.strip().upper() not in ("BEGIN;", "COMMIT;")]
    return "\n".join(lines)


def upgrade() -> None:
    op.execute(_statements(SCHEMAS / "roles.sql"))
    op.execute(_statements(SCHEMAS / "schema.sql"))


def downgrade() -> None:
    raise NotImplementedError("pas de retour arrière du schéma initial : restaurer une sauvegarde")
