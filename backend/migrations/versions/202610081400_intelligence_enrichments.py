"""intelligence: article_enrichments, article_entities

Revision ID: 202610081400
Revises: 202610081300
Create Date: 2026-10-08 14:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610081400"
down_revision: str | None = "202610081300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_enrichments",
        sa.Column(
            "article_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("ingestion.articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("language", sa.Text()),
        sa.Column("sport_id", sa.Text(), sa.ForeignKey("taxonomy.sports.id")),
        sa.Column("competition_id", pg.UUID(as_uuid=True), sa.ForeignKey("taxonomy.entities.id")),
        sa.Column("relevance", sa.Text(), nullable=False),
        sa.Column("relevance_rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("clickbait", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rumor_markers", pg.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("event_date_hint", sa.Date()),
        sa.Column("claims", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "raw_entities", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("headline", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding", Vector(1024)),
        sa.Column("embedding_model", sa.Text()),
        sa.Column("method", sa.Text(), nullable=False, server_default="rules"),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("ai_run_id", pg.UUID(as_uuid=True)),
        sa.Column("copied_from", pg.UUID(as_uuid=True)),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relevance IN ('HIGH','MEDIUM','LOW','IRRELEVANT')",
            name="ck_article_enrichments_relevance",
        ),
        sa.CheckConstraint("method IN ('rules','llm')", name="ck_article_enrichments_method"),
        schema="intelligence",
    )
    op.execute(
        "CREATE INDEX ix_article_enrichments_embedding ON intelligence.article_enrichments USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.create_table(
        "article_entities",
        sa.Column(
            "article_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("ingestion.articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("taxonomy.entities.id"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("mentions", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("article_id", "entity_id"),
        schema="intelligence",
    )
    op.create_index(
        "ix_article_entities_entity_id", "article_entities", ["entity_id"], schema="intelligence"
    )


def downgrade() -> None:
    op.drop_table("article_entities", schema="intelligence")
    op.drop_table("article_enrichments", schema="intelligence")
