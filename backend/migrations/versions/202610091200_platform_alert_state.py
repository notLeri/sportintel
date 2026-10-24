"""platform: alert_state (BE-T4.13)

Revision ID: 202610091200
Revises: 202610091100
Create Date: 2026-10-09 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610091200"
down_revision: str | None = "202610091100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_state",
        sa.Column("alert_key", sa.Text(), primary_key=True),
        sa.Column("firing", sa.Boolean(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True)),
        sa.Column("details", pg.JSONB()),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("alert_state", schema="platform")
