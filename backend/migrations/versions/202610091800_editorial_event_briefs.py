"""editorial: AI-брифы событий по языкам; events.title_i18n — переведённый заголовок для списка

Revision ID: 202610091800
Revises: 202610091700
Create Date: 2026-10-09 18:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610091800"
down_revision: str | None = "202610091700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("title_i18n", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="events",
    )
    op.create_table(
        "event_briefs",
        sa.Column(
            "event_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("events.events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lang", sa.Text(), nullable=False),
        sa.Column("brief", pg.JSONB(), nullable=False),
        sa.Column("sources", pg.JSONB(), nullable=False),
        sa.Column("article_hash", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("event_id", "lang"),
        sa.CheckConstraint("lang IN ('pt-BR','en','ru')", name="ck_event_briefs_lang"),
        schema="editorial",
    )


def downgrade() -> None:
    op.drop_table("event_briefs", schema="editorial")
    op.drop_column("events", "title_i18n", schema="events")
