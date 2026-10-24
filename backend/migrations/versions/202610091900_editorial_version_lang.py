"""editorial: язык у версии черновика — пост можно подготовить на другом языке (из AI-брифа)

Revision ID: 202610091900
Revises: 202610091800
Create Date: 2026-10-09 19:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610091900"
down_revision: str | None = "202610091800"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Все прежние версии писались на languages.telegram_language (по умолчанию pt-BR).
    op.add_column(
        "telegram_draft_versions",
        sa.Column("lang", sa.Text(), nullable=False, server_default="pt-BR"),
        schema="editorial",
    )


def downgrade() -> None:
    op.drop_column("telegram_draft_versions", "lang", schema="editorial")
