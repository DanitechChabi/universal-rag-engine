"""Phase 2 : réindexation selon le moteur OCR, colonnes des passages suspects.

Revision ID: 0002
Revises: 0001
"""

from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute((Path(__file__).resolve().parents[1] / "sql" / "0002_ocr_suspicion.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
