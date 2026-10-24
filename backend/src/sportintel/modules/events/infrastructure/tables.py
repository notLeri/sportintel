from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID

from sportintel.platform.db_metadata import register

metadata = register(MetaData(schema="events"))
NOW = text("now()")
RANK_SQL = "CASE relevance WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0 END"

events = Table(
    "events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("title", Text, nullable=False),
    Column("title_origin", Text, nullable=False),
    Column("summary", Text),
    Column("summary_origin", Text),
    Column("summary_citations", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("summary_grounding", JSONB),
    Column("summary_generated_at", DateTime(timezone=True)),
    Column("summary_article_set_hash", Text),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_article_at", DateTime(timezone=True), nullable=False),
    Column("sport_id", Text, ForeignKey("taxonomy.sports.id")),
    Column("region", Text, index=True),
    Column("title_i18n", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("summary_i18n", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("competition_id", UUID(as_uuid=True), ForeignKey("taxonomy.entities.id")),
    Column("relevance", Text, nullable=False, server_default="LOW"),
    Column("relevance_rank", SmallInteger, Computed(RANK_SQL, persisted=True)),
    Column("relevance_rationale", Text, nullable=False, server_default=""),
    Column("relevance_origin", Text, nullable=False, server_default="rule"),
    Column("relevance_reason", Text),
    Column("reliability", Text, nullable=False, server_default="UNKNOWN"),
    Column("reliability_factors", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("reliability_origin", Text, nullable=False, server_default="rule"),
    Column("reliability_reason", Text),
    Column("status", Text, nullable=False, server_default="NEW"),
    Column("status_changed_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("rejection_reason", Text),
    Column("rejection_comment", Text),
    Column("assignee_id", UUID(as_uuid=True)),
    Column("manual_overrides", ARRAY(Text), nullable=False, server_default="{}"),
    Column("has_updates_since_edit", Boolean, nullable=False, server_default=text("false")),
    Column("has_open_conflicts", Boolean, nullable=False, server_default=text("false")),
    Column("stale_suspected", Boolean, nullable=False, server_default=text("false")),
    Column("has_clickbait", Boolean, nullable=False, server_default=text("false")),
    Column("article_count", Integer, nullable=False, server_default="0"),
    Column("source_count", Integer, nullable=False, server_default="0"),
    Column("independent_source_count", Integer, nullable=False, server_default="0"),
    Column("centroid", Vector(1024)),
    Column("source_ids", ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"),
    Column("origin", Text, nullable=False, server_default="auto"),
    Column("created_by", UUID(as_uuid=True)),
    Column("refresh_requested_at", DateTime(timezone=True)),
    Column("draft_state", Text),
    Column("draft_last_human_author_id", UUID(as_uuid=True)),
    Column("search_doc", Text, nullable=False, server_default=""),
    Column(
        "search_tsv", TSVECTOR, Computed("to_tsvector('pt_unaccent', search_doc)", persisted=True)
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("version", Integer, nullable=False, server_default="1"),
)

event_articles = Table(
    "event_articles",
    metadata,
    Column("article_id", UUID(as_uuid=True), ForeignKey("ingestion.articles.id"), primary_key=True),
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("events.events.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("attached_at", DateTime(timezone=True), nullable=False),
    Column("attach_score", Float),
    Column("attach_method", Text, nullable=False),
    Column("cluster_locked", Boolean, nullable=False, server_default=text("false")),
    Column("is_duplicate", Boolean, nullable=False, server_default=text("false")),
)

event_entities = Table(
    "event_entities",
    metadata,
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("events.events.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("entity_id", UUID(as_uuid=True), ForeignKey("taxonomy.entities.id"), nullable=False),
    Column("role", Text, nullable=False),
    Column("mentions", Integer, nullable=False, server_default="1"),
    Column("manual", Boolean, nullable=False, server_default=text("false")),
    PrimaryKeyConstraint("event_id", "entity_id"),
)

event_relations = Table(
    "event_relations",
    metadata,
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("events.events.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "related_event_id",
        UUID(as_uuid=True),
        ForeignKey("events.events.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("kind", Text, nullable=False),
    Column("score", Float),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    PrimaryKeyConstraint("event_id", "related_event_id", "kind"),
)
