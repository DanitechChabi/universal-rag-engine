"""Métriques de supervision (agrégats sans contenu).

Revision ID: 0008
Revises: 0007
"""

from pathlib import Path

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0008_metriques_de_supervision.sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
