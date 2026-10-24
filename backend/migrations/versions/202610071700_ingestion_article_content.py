"""ingestion: article_content

Revision ID: 202610071700
Revises: 202610071610
Create Date: 2026-10-07 17:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610071700"
down_revision: str | None = "202610071610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_content",
        sa.Column(
            "article_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("ingestion.articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        schema="ingestion",
    )
    op.create_index(
        "ix_article_content_expires_at", "article_content", ["expires_at"], schema="ingestion"
    )


def downgrade() -> None:
    op.drop_table("article_content", schema="ingestion")
