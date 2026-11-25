"""Phase 3 : identifiant et courriel des identités externes ; seules les correspondances confirmées donnent des droits.

Revision ID: 0003
Revises: 0002
"""

from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0003_identites_externes.sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
