from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from sportintel.platform.db_metadata import register

metadata = register(MetaData(schema="editorial"))
NOW = text("now()")

telegram_drafts = Table(
    "telegram_drafts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("events.events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    Column("state", Text, nullable=False),
    Column("current_version", Integer, nullable=False, server_default="0"),
    Column("failure_code", Text),
    Column("created_by", UUID(as_uuid=True)),
    Column("auto_basis_hash", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("version", Integer, nullable=False, server_default="1"),
)

# AI-бриф события на конкретном языке; пересобирается при смене состава статей.
event_briefs = Table(
    "event_briefs",
    metadata,
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("events.events.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("lang", Text, nullable=False),
    Column("brief", JSONB, nullable=False),
    Column("sources", JSONB, nullable=False),
    Column("article_hash", Text, nullable=False),
    Column("provider", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column("duration_ms", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    PrimaryKeyConstraint("event_id", "lang"),
)

telegram_draft_versions = Table(
    "telegram_draft_versions",
    metadata,
    Column(
        "draft_id",
        UUID(as_uuid=True),
        ForeignKey("editorial.telegram_drafts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("n", Integer, nullable=False),
    Column("lang", Text, nullable=False, server_default="pt-BR"),  # язык поста этой версии
    Column("body_tg_html", Text, nullable=False),
    Column("image_url", Text),
    Column("disclaimer_kinds", ARRAY(Text), nullable=False, server_default="{}"),
    Column("disclaimer_removed", Boolean, nullable=False, server_default=text("false")),
    Column("origin", Text, nullable=False),
    Column("citations", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("grounding_report", JSONB),
    Column("prompt_version", Text),
    Column("ai_run_id", UUID(as_uuid=True)),
    Column("author_id", UUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    PrimaryKeyConstraint("draft_id", "n"),
)


# Каналы публикации (фаза 6): фильтры, режим и расписание. Токен бота — только в env.
channels = Table(
    "channels",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False),
    Column("tg_chat_id", Text, nullable=False),
    Column("language", Text, nullable=False),
    Column("mode", Text, nullable=False),
    Column("cron", Text, nullable=False),
    Column("format", Text, nullable=False),
    Column("max_per_run", Integer, nullable=False),
    Column("min_relevance", Text, nullable=False),
    Column("min_trust", Text, nullable=False),
    Column("min_tier", Text),
    Column("regions", ARRAY(Text), nullable=False, server_default="{}"),
    Column("sports", ARRAY(Text), nullable=False, server_default="{}"),
    Column("source_allow", ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"),
    Column("source_deny", ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("last_run_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("version", Integer, nullable=False, server_default="1"),
)

# Что и когда ушло в канал. UNIQUE(channel_id, event_id): событие не публикуется дважды.
publications = Table(
    "publications",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "channel_id",
        UUID(as_uuid=True),
        ForeignKey("editorial.channels.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("events.events.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("status", Text, nullable=False),
    Column("lang", Text, nullable=False),
    Column("body_tg_html", Text, nullable=False),
    Column("tg_message_id", Integer),
    Column("error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("channel_id", "event_id", name="uq_publications_channel_event"),
)

channel_pins = Table(
    "channel_pins",
    metadata,
    Column(
        "channel_id",
        UUID(as_uuid=True),
        ForeignKey("editorial.channels.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("events.events.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("publish_at", DateTime(timezone=True), nullable=False),
    Column("created_by", UUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)

translations = Table(
    "translations",
    metadata,
    Column("key", Text, primary_key=True),  # sha256(lang, формат, исходный текст)
    Column("lang", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
