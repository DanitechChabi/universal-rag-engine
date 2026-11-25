"""Phase 3 : contexte du document et version du traitement d'indexation (ADR-0021).

Revision ID: 0005
Revises: 0004
"""

from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0005_contexte_et_version_du_traitement.sql").read_text(
            encoding="utf-8"
        )
    )


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
