from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from sportintel.platform.db_metadata import register

metadata = register(MetaData(schema="sources"))
NOW = text("now()")

sources = Table(
    "sources",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False),
    Column("domain", Text, nullable=False),
    Column("base_url", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("feed_urls", ARRAY(Text), nullable=False, server_default="{}"),
    Column("parser_profile", Text, nullable=False, server_default="default"),
    Column("tier", Text, nullable=True),
    Column("owner_group", Text, nullable=True),
    Column("language", Text, nullable=False, server_default="pt-BR"),
    Column("region", Text, nullable=False, server_default="BR"),
    Column("poll_interval_seconds", Integer, nullable=False, server_default=text("300")),
    Column("min_request_gap_ms", Integer, nullable=False, server_default=text("2000")),
    Column("content_policy", Text, nullable=False, server_default="transient_text"),
    Column("content_ttl_days", Integer, nullable=False, server_default=text("7")),
    Column("url_keep_params", ARRAY(Text), nullable=False, server_default="{}"),
    Column("tos_notes", Text, nullable=False, server_default=""),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("health", Text, nullable=False, server_default="unknown"),
    Column("consecutive_failures", Integer, nullable=False, server_default=text("0")),
    Column("next_poll_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("last_success_at", DateTime(timezone=True), nullable=True),
    Column("last_new_article_at", DateTime(timezone=True), nullable=True),
    Column("feed_cache", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("version", Integer, nullable=False, server_default=text("1")),
    # Домен не уникален: несколько Telegram-каналов на t.me различаются base_url.
    UniqueConstraint("domain", "base_url", name="sources_domain_base_url_key"),
    CheckConstraint("kind IN ('rss','sitemap','html','manual','calendar')", name="ck_sources_kind"),
    CheckConstraint("region ~ '^[A-Z]{2}$'", name="ck_sources_region"),
    CheckConstraint("tier IN ('OFFICIAL','A','B','C','UNTRUSTED')", name="ck_sources_tier"),
    CheckConstraint(
        "poll_interval_seconds BETWEEN 60 AND 86400", name="ck_sources_poll_interval_seconds"
    ),
    CheckConstraint(
        "min_request_gap_ms BETWEEN 500 AND 60000", name="ck_sources_min_request_gap_ms"
    ),
    CheckConstraint(
        "content_policy IN ('snippet_only','transient_text')", name="ck_sources_content_policy"
    ),
    CheckConstraint("content_ttl_days BETWEEN 1 AND 30", name="ck_sources_content_ttl_days"),
    CheckConstraint("health IN ('unknown','ok','degraded','down')", name="ck_sources_health"),
    Index("ix_sources_active_next_poll_at", "active", "next_poll_at"),
)
