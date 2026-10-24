"""ingestion.articles.i18n — перевод заголовка и лида статьи на язык интерфейса

{lang: {"title": ..., "lead": ...}}; заполняет editorial.translate_event вместе с переводом события.

Revision ID: 202610111000
Revises: 202610101400
Create Date: 2026-10-11 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610111000"
down_revision: str | None = "202610101400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("i18n", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="ingestion",
    )


def downgrade() -> None:
    op.drop_column("articles", "i18n", schema="ingestion")
