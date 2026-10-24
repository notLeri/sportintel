"""taxonomy: unlinked_mentions

Revision ID: 202610081200
Revises: 202610081110
Create Date: 2026-10-08 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610081200"
down_revision: str | None = "202610081110"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "unlinked_mentions",
        sa.Column("mention_norm", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("sport_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("sport_id", sa.Text(), nullable=True),
        sa.Column("mention", sa.Text(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_article_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="open"),
        sa.CheckConstraint(
            "state IN ('open','resolved','ignored')", name="ck_unlinked_mentions_state"
        ),
        sa.PrimaryKeyConstraint("mention_norm", "kind", "sport_key"),
        schema="taxonomy",
    )


def downgrade() -> None:
    op.drop_table("unlinked_mentions", schema="taxonomy")
