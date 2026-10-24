"""sources: sources table

Revision ID: 202610071500
Revises: 202610071400
Create Date: 2026-10-07 15:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610071500"
down_revision: str | None = "202610071400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("feed_urls", pg.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("parser_profile", sa.Text(), nullable=False, server_default="default"),
        sa.Column("tier", sa.Text(), nullable=True),
        sa.Column("owner_group", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=False, server_default="pt-BR"),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("min_request_gap_ms", sa.Integer(), nullable=False, server_default="2000"),
        sa.Column("content_policy", sa.Text(), nullable=False, server_default="transient_text"),
        sa.Column("content_ttl_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("url_keep_params", pg.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("tos_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("health", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_new_article_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feed_cache", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("domain", name="sources_domain_key"),
        sa.CheckConstraint("kind IN ('rss','sitemap','html','manual')", name="ck_sources_kind"),
        sa.CheckConstraint("tier IN ('OFFICIAL','A','B','C')", name="ck_sources_tier"),
        sa.CheckConstraint(
            "poll_interval_seconds BETWEEN 60 AND 86400", name="ck_sources_poll_interval_seconds"
        ),
        sa.CheckConstraint(
            "min_request_gap_ms BETWEEN 500 AND 60000", name="ck_sources_min_request_gap_ms"
        ),
        sa.CheckConstraint(
            "content_policy IN ('snippet_only','transient_text')", name="ck_sources_content_policy"
        ),
        sa.CheckConstraint("content_ttl_days BETWEEN 1 AND 30", name="ck_sources_content_ttl_days"),
        sa.CheckConstraint(
            "health IN ('unknown','ok','degraded','down')", name="ck_sources_health"
        ),
        schema="sources",
    )
    op.create_index(
        "ix_sources_active_next_poll_at", "sources", ["active", "next_poll_at"], schema="sources"
    )


def downgrade() -> None:
    op.drop_table("sources", schema="sources")
