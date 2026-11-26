"""Reprise des tâches abandonnées, même sans autre tâche prête.

Revision ID: 0009
Revises: 0008
"""

from pathlib import Path

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0009_reprise_des_taches_abandonnees.sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
