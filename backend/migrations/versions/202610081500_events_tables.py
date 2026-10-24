"""events: events, event_articles, event_entities, event_relations

Revision ID: 202610081500
Revises: 202610081400
Create Date: 2026-10-08 15:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610081500"
down_revision: str | None = "202610081400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
NOW = sa.text("now()")
U = pg.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", U, primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_origin", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("summary_origin", sa.Text()),
        sa.Column(
            "summary_citations", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("summary_grounding", pg.JSONB()),
        sa.Column("summary_generated_at", TS),
        sa.Column("summary_article_set_hash", sa.Text()),
        sa.Column("occurred_at", TS, nullable=False),
        sa.Column("first_seen_at", TS, nullable=False),
        sa.Column("last_article_at", TS, nullable=False),
        sa.Column("sport_id", sa.Text(), sa.ForeignKey("taxonomy.sports.id")),
        sa.Column("competition_id", U, sa.ForeignKey("taxonomy.entities.id")),
        sa.Column("relevance", sa.Text(), nullable=False, server_default="LOW"),
        sa.Column(
            "relevance_rank",
            sa.SmallInteger(),
            sa.Computed(
                "CASE relevance WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0 END",
                persisted=True,
            ),
        ),
        sa.Column("relevance_rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("relevance_origin", sa.Text(), nullable=False, server_default="rule"),
        sa.Column("relevance_reason", sa.Text()),
        sa.Column("reliability", sa.Text(), nullable=False, server_default="UNKNOWN"),
        sa.Column(
            "reliability_factors", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("reliability_origin", sa.Text(), nullable=False, server_default="rule"),
        sa.Column("reliability_reason", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="NEW"),
        sa.Column("status_changed_at", TS, nullable=False, server_default=NOW),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("rejection_comment", sa.Text()),
        sa.Column("assignee_id", U),
        sa.Column("manual_overrides", pg.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "has_updates_since_edit", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("has_open_conflicts", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stale_suspected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_clickbait", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("independent_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("centroid", Vector(1024)),
        sa.Column("source_ids", pg.ARRAY(U), nullable=False, server_default="{}"),
        sa.Column("origin", sa.Text(), nullable=False, server_default="auto"),
        sa.Column("created_by", U),
        sa.Column("refresh_requested_at", TS),
        sa.Column("draft_state", sa.Text()),
        sa.Column("draft_last_human_author_id", U),
        sa.Column("search_doc", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "search_tsv",
            pg.TSVECTOR(),
            sa.Computed("to_tsvector('pt_unaccent', search_doc)", persisted=True),
        ),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 300", name="ck_events_title"),
        sa.CheckConstraint(
            "title_origin IN ('ai','human','source','template')", name="ck_events_title_origin"
        ),
        sa.CheckConstraint(
            "summary_origin IN ('ai','human','source','template')", name="ck_events_summary_origin"
        ),
        sa.CheckConstraint(
            "relevance IN ('HIGH','MEDIUM','LOW','IRRELEVANT')", name="ck_events_relevance"
        ),
        sa.CheckConstraint(
            "relevance_origin IN ('ai','rule','human')", name="ck_events_relevance_origin"
        ),
        sa.CheckConstraint(
            "reliability IN ('HIGH','MEDIUM','LOW','UNKNOWN')", name="ck_events_reliability"
        ),
        sa.CheckConstraint(
            "reliability_origin IN ('rule','human')", name="ck_events_reliability_origin"
        ),
        sa.CheckConstraint(
            "status IN ('NEW','REVIEWING','SELECTED','DRAFT','READY','PUBLISHED','REJECTED')",
            name="ck_events_status",
        ),
        sa.CheckConstraint(
            "rejection_reason IN ('DUPLICATE','IRRELEVANT','LOW_QUALITY','INCORRECT','OLD_NEWS','NOT_TELEGRAM_WORTHY','OTHER')",
            name="ck_events_rejection_reason",
        ),
        sa.CheckConstraint("origin IN ('auto','manual')", name="ck_events_origin"),
        sa.CheckConstraint(
            "draft_state IN ('generating','ready','failed')", name="ck_events_draft_state"
        ),
        sa.CheckConstraint(
            "(status = 'REJECTED') = (rejection_reason IS NOT NULL)", name="ck_events_rejection"
        ),
        sa.CheckConstraint(
            "rejection_reason <> 'OTHER' OR coalesce(rejection_comment,'') <> ''",
            name="ck_events_other_comment",
        ),
        schema="events",
    )
    for sql in (
        "CREATE INDEX ix_events_rank_recent ON events.events (relevance_rank DESC, last_article_at DESC, id DESC)",
        "CREATE INDEX ix_events_recent ON events.events (last_article_at DESC, id DESC)",
        "CREATE INDEX ix_events_sport_recent ON events.events (sport_id, last_article_at DESC)",
        "CREATE INDEX ix_events_competition_recent ON events.events (competition_id, last_article_at DESC)",
        "CREATE INDEX ix_events_status_recent ON events.events (status, last_article_at DESC)",
        "CREATE INDEX ix_events_search_tsv ON events.events USING gin (search_tsv)",
        "CREATE INDEX ix_events_source_ids ON events.events USING gin (source_ids)",
        "CREATE INDEX ix_events_centroid ON events.events USING hnsw (centroid vector_cosine_ops)",
        "CREATE INDEX ix_events_refresh_requested_at ON events.events (refresh_requested_at) WHERE refresh_requested_at IS NOT NULL",
        "CREATE INDEX ix_events_title_trgm ON events.events USING gin (platform.immutable_unaccent(lower(title)) gin_trgm_ops)",
    ):
        op.execute(sql)
    op.create_table(
        "event_articles",
        sa.Column("article_id", U, sa.ForeignKey("ingestion.articles.id"), primary_key=True),
        sa.Column(
            "event_id", U, sa.ForeignKey("events.events.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("attached_at", TS, nullable=False),
        sa.Column("attach_score", sa.Float()),
        sa.Column("attach_method", sa.Text(), nullable=False),
        sa.Column("cluster_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "attach_method IN ('new','auto','adjudicated','syndication','manual')",
            name="ck_event_articles_attach_method",
        ),
        schema="events",
    )
    op.create_index("ix_event_articles_event_id", "event_articles", ["event_id"], schema="events")
    op.create_table(
        "event_entities",
        sa.Column(
            "event_id", U, sa.ForeignKey("events.events.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("entity_id", U, sa.ForeignKey("taxonomy.entities.id"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("mentions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("event_id", "entity_id"),
        sa.CheckConstraint(
            "role IN ('competition','team','player','coach','person','venue')",
            name="ck_event_entities_role",
        ),
        schema="events",
    )
    op.create_index(
        "ix_event_entities_entity_id_event_id",
        "event_entities",
        ["entity_id", "event_id"],
        schema="events",
    )
    op.create_table(
        "event_relations",
        sa.Column(
            "event_id", U, sa.ForeignKey("events.events.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "related_event_id",
            U,
            sa.ForeignKey("events.events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.PrimaryKeyConstraint("event_id", "related_event_id", "kind"),
        sa.CheckConstraint(
            "kind IN ('related','follow_up','possible_duplicate','old_news')",
            name="ck_event_relations_kind",
        ),
        sa.CheckConstraint("event_id <> related_event_id", name="ck_event_relations_self"),
        schema="events",
    )


def downgrade() -> None:
    for t in ("event_relations", "event_entities", "event_articles", "events"):
        op.drop_table(t, schema="events")
