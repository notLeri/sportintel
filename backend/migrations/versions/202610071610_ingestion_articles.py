"""ingestion: articles

Revision ID: 202610071610
Revises: 202610071600
Create Date: 2026-10-07 16:10:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610071610"
down_revision: str | None = "202610071600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
SEARCH_TSV = (
    "setweight(to_tsvector('pt_unaccent', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('pt_unaccent', coalesce(lead, '')), 'B')"
)


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id", pg.UUID(as_uuid=True), sa.ForeignKey("sources.sources.id"), nullable=False
        ),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("lead", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.BigInteger(), nullable=True),
        sa.Column(
            "duplicate_of",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("ingestion.articles.id"),
            nullable=True,
        ),
        sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("target_event_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="discovered"),
        sa.Column(
            "state_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("search_tsv", pg.TSVECTOR(), sa.Computed(SEARCH_TSV, persisted=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("canonical_url", name="ux_articles_canonical_url"),
        sa.CheckConstraint(
            "state IN ('discovered','extracted','enriched','clustered','failed')",
            name="ck_articles_state",
        ),
        schema="ingestion",
    )
    op.create_index(
        "ix_articles_source_id_published_at",
        "articles",
        ["source_id", "published_at"],
        schema="ingestion",
    )
    op.create_index(
        "ix_articles_state_state_changed_at",
        "articles",
        ["state", "state_changed_at"],
        schema="ingestion",
    )
    op.execute(
        "CREATE INDEX ix_articles_discovered_at ON ingestion.articles (discovered_at DESC, id DESC)"
    )
    op.execute("CREATE INDEX ix_articles_search_tsv ON ingestion.articles USING gin (search_tsv)")


def downgrade() -> None:
    op.drop_table("articles", schema="ingestion")
