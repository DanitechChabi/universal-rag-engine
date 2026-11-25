"""Sommaires et index reconnus (type de fragment « navigation »).

Revision ID: 0006
Revises: 0005
"""

from pathlib import Path

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0006_passages_de_navigation.sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
