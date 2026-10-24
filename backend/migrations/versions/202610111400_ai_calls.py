"""platform.ai_calls — учёт обращений к ИИ: прогресс в интерфейсе и нагрузка в аналитике

Revision ID: 202610111400
Revises: 202610111200
Create Date: 2026-10-11 14:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610111400"
down_revision: str | None = "202610111200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("event_id", pg.UUID(as_uuid=True)),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),  # NULL — ещё идёт
        sa.Column("ok", sa.Boolean),
        schema="platform",
    )
    op.create_index("ix_ai_calls_started_at", "ai_calls", ["started_at"], schema="platform")


def downgrade() -> None:
    op.drop_table("ai_calls", schema="platform")
