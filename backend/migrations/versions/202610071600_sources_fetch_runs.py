"""sources: fetch_runs

Revision ID: 202610071600
Revises: 202610071510
Create Date: 2026-10-07 16:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610071600"
down_revision: str | None = "202610071510"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fetch_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("sources.sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feed_url", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ok','not_modified','error','skipped')", name="ck_fetch_runs_status"
        ),
        schema="sources",
    )
    op.execute(
        "CREATE INDEX ix_fetch_runs_source_id_started_at "
        "ON sources.fetch_runs (source_id, started_at DESC)"
    )


def downgrade() -> None:
    op.drop_table("fetch_runs", schema="sources")
