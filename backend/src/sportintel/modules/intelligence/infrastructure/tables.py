from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from sportintel.platform.db_metadata import register

metadata = register(MetaData(schema="intelligence"))
EMBEDDING_DIM = 1024

article_enrichments = Table(
    "article_enrichments",
    metadata,
    Column(
        "article_id",
        UUID(as_uuid=True),
        ForeignKey("ingestion.articles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("language", Text),
    Column("sport_id", Text, ForeignKey("taxonomy.sports.id")),
    Column("competition_id", UUID(as_uuid=True), ForeignKey("taxonomy.entities.id")),
    Column("relevance", Text, nullable=False),
    Column("relevance_rationale", Text, nullable=False, server_default=""),
    Column("clickbait", Boolean, nullable=False, server_default=text("false")),
    Column("rumor_markers", ARRAY(Text), nullable=False, server_default="{}"),
    Column("event_date_hint", Date),
    Column("claims", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("raw_entities", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("headline", Text, nullable=False, server_default=""),
    Column("embedding", Vector(EMBEDDING_DIM)),
    Column("embedding_model", Text),
    Column("method", Text, nullable=False, server_default="rules"),
    Column("prompt_version", Text, nullable=False),
    Column("ai_run_id", UUID(as_uuid=True)),
    Column("copied_from", UUID(as_uuid=True)),
    Column("enriched_at", DateTime(timezone=True), nullable=False),
)

article_entities = Table(
    "article_entities",
    metadata,
    Column(
        "article_id",
        UUID(as_uuid=True),
        ForeignKey("ingestion.articles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("entity_id", UUID(as_uuid=True), ForeignKey("taxonomy.entities.id"), nullable=False),
    Column("role", Text, nullable=False),
    Column("mentions", Integer, nullable=False, server_default="1"),
    PrimaryKeyConstraint("article_id", "entity_id"),
    Index("ix_article_entities_entity_id", "entity_id"),
)
