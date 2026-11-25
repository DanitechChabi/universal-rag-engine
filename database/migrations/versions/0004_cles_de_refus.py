"""Phase 3 : clés de refus (refus explicites des sources, ADR-0020).

Revision ID: 0004
Revises: 0003
"""

from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute((Path(__file__).resolve().parents[1] / "sql" / "0004_cles_de_refus.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
