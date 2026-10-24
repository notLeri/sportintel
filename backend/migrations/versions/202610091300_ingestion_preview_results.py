"""ingestion: preview_results (BE-T4.8)

Revision ID: 202610091300
Revises: 202610091200
Create Date: 2026-10-09 13:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610091300"
down_revision: str | None = "202610091200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preview_results",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", pg.UUID(as_uuid=True)),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("result", pg.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("status IN ('pending','ok','error')", name="ck_preview_results_status"),
        schema="ingestion",
    )


def downgrade() -> None:
    op.drop_table("preview_results", schema="ingestion")
