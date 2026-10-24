"""platform: app_settings

Revision ID: 202610081300
Revises: 202610081200
Create Date: 2026-10-08 13:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610081300"
down_revision: str | None = "202610081200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", pg.JSONB(), nullable=False),
        sa.Column("updated_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("app_settings", schema="platform")
