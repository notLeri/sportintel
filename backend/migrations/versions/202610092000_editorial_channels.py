"""editorial: каналы Telegram (фильтры, режим, расписание) и журнал публикаций

Revision ID: 202610092000
Revises: 202610091900
Create Date: 2026-10-09 20:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610092000"
down_revision: str | None = "202610091900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tg_chat_id", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("cron", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("max_per_run", sa.Integer(), nullable=False),
        sa.Column("min_relevance", sa.Text(), nullable=False),
        sa.Column("min_trust", sa.Text(), nullable=False),
        sa.Column("min_tier", sa.Text()),
        sa.Column("regions", pg.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("sports", pg.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "source_allow", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "source_deny", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("mode IN ('approval','auto')", name="ck_channels_mode"),
        sa.CheckConstraint("format IN ('single','digest')", name="ck_channels_format"),
        sa.CheckConstraint("language IN ('pt-BR','en','ru')", name="ck_channels_language"),
        sa.CheckConstraint("max_per_run BETWEEN 1 AND 20", name="ck_channels_max_per_run"),
        schema="editorial",
    )
    op.create_table(
        "publications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("editorial.channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("events.events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=False),
        sa.Column("body_tg_html", sa.Text(), nullable=False),
        sa.Column("tg_message_id", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("channel_id", "event_id", name="uq_publications_channel_event"),
        sa.CheckConstraint("status IN ('sent','failed')", name="ck_publications_status"),
        schema="editorial",
    )


def downgrade() -> None:
    op.drop_table("publications", schema="editorial")
    op.drop_table("channels", schema="editorial")
