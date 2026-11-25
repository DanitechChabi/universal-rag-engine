"""Fournisseurs externes OpenRouter, Groq et Mistral (compatibles OpenAI).

Revision ID: 0007
Revises: 0006
"""

from pathlib import Path

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0007_fournisseurs_openrouter_groq_mistral.sql").read_text(
            encoding="utf-8"
        )
    )


def downgrade() -> None:
    raise NotImplementedError("restaurer une sauvegarde")
