"""editorial.channel_pins — пост события закреплён на время (перетаскивание на календарь)

Закреплённое событие уходит в своё время, а не в очередной запуск по cron.

Revision ID: 202610111200
Revises: 202610111100
Create Date: 2026-10-11 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610111200"
down_revision: str | None = "202610111100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_pins",
        sa.Column(
            "channel_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("editorial.channels.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "event_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("events.events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="editorial",
    )


def downgrade() -> None:
    op.drop_table("channel_pins", schema="editorial")
