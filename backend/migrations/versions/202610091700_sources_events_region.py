"""sources/events: регион (ISO 3166-1 alpha-2) — события не смешивают страны

Revision ID: 202610091700
Revises: 202610091600
Create Date: 2026-10-09 17:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610091700"
down_revision: str | None = "202610091600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("region", sa.Text(), nullable=False, server_default="BR"),
        schema="sources",
    )
    op.create_check_constraint(
        "ck_sources_region", "sources", "region ~ '^[A-Z]{2}$'", schema="sources"
    )
    op.add_column("events", sa.Column("region", sa.Text()), schema="events")
    op.execute("UPDATE events.events SET region = 'BR'")
    op.create_index("ix_events_region", "events", ["region"], schema="events")


def downgrade() -> None:
    op.drop_index("ix_events_region", "events", schema="events")
    op.drop_column("events", "region", schema="events")
    op.drop_constraint("ck_sources_region", "sources", schema="sources")
    op.drop_column("sources", "region", schema="sources")
