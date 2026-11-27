"""Limite des échecs de connexion par adresse.

Revision ID: 0010
Revises: 0009
"""

from pathlib import Path

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0010_limite_des_echecs_par_adresse.sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
