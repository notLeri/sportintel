from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

from sportintel.platform.db_metadata import register

metadata = register(MetaData(schema="ingestion"))
NOW = text("now()")
SEARCH_TSV = (
    "setweight(to_tsvector('pt_unaccent', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('pt_unaccent', coalesce(lead, '')), 'B')"
)

articles = Table(
    "articles",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("source_id", UUID(as_uuid=True), ForeignKey("sources.sources.id"), nullable=False),
    Column("canonical_url", Text, nullable=False, unique=True),
    Column("original_url", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("lead", Text, nullable=True),
    # {lang: {"title": ..., "lead": ...}} — перевод ИИ на язык интерфейса (editorial.translate_event)
    Column("i18n", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("discovered_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("image_url", Text, nullable=True),
    Column("author", Text, nullable=True),
    Column("language", Text, nullable=True),
    Column("content_hash", BigInteger, nullable=True),
    Column("duplicate_of", UUID(as_uuid=True), ForeignKey("ingestion.articles.id"), nullable=True),
    Column("manual", Boolean, nullable=False, server_default=text("false")),
    Column("added_by", UUID(as_uuid=True), nullable=True),
    Column("target_event_id", UUID(as_uuid=True), nullable=True),  # без FK: events зависит от нас
    Column("state", Text, nullable=False, server_default="discovered"),
    Column("state_changed_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("failure_code", Text, nullable=True),
    Column("failure_detail", Text, nullable=True),
    Column("search_tsv", TSVECTOR, Computed(SEARCH_TSV, persisted=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    CheckConstraint(
        "state IN ('discovered','extracted','enriched','clustered','failed')",
        name="ck_articles_state",
    ),
    Index("ix_articles_source_id_published_at", "source_id", "published_at"),
    Index("ix_articles_state_state_changed_at", "state", "state_changed_at"),
)
