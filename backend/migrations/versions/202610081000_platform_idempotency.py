"""platform: idempotency_keys

Revision ID: 202610081000
Revises: 202610071700
Create Date: 2026-10-08 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610081000"
down_revision: str | None = "202610071700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.LargeBinary(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", pg.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id", "key"),
        schema="platform",
    )
    op.create_index(
        "ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"], schema="platform"
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema="platform")
