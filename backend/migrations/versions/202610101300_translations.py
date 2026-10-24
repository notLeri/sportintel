"""events.summary_i18n — перевод сводки; editorial.translations — кеш переводов ИИ

summary_i18n: {lang: {"h": sha256 исходной сводки, "t": перевод}} — устаревший перевод виден по h.
translations: одинаковый текст на тот же язык ИИ переводит один раз (заголовки, сводки, черновики).

Revision ID: 202610101300
Revises: 202610101200
Create Date: 2026-10-10 13:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610101300"
down_revision: str | None = "202610101200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "summary_i18n", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        schema="events",
    )
    op.create_table(
        "translations",
        sa.Column("key", sa.Text(), primary_key=True),  # sha256(lang, формат, исходный текст)
        sa.Column("lang", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="editorial",
    )


def downgrade() -> None:
    op.drop_table("translations", schema="editorial")
    op.drop_column("events", "summary_i18n", schema="events")
