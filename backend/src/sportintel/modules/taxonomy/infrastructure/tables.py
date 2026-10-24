from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from sportintel.platform.db_metadata import register

metadata = register(MetaData(schema="taxonomy"))
NOW = text("now()")

sports = Table(
    "sports",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name_i18n", JSONB, nullable=False),
    Column("sort", Integer, nullable=False, server_default="100"),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    CheckConstraint("id ~ '^[a-z0-9_]{2,32}$'", name="ck_sports_id"),
)

entities = Table(
    "entities",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("kind", Text, nullable=False),
    Column("sport_id", Text, ForeignKey("taxonomy.sports.id"), nullable=True),
    Column("canonical_name", Text, nullable=False),
    # название для показа по языкам интерфейса; canonical_name — для поиска в текстах источников
    Column("name_i18n", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("name_norm", Text, nullable=False),
    Column("country", Text, nullable=True),
    Column("external_ids", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("priority", SmallInteger, nullable=False, server_default="0"),
    Column("auto_created", Boolean, nullable=False, server_default=text("false")),
    Column("review_state", Text, nullable=False, server_default="approved"),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("version", Integer, nullable=False, server_default="1"),
)

entity_aliases = Table(
    "entity_aliases",
    metadata,
    Column(
        "entity_id",
        UUID(as_uuid=True),
        ForeignKey("taxonomy.entities.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("alias", Text, nullable=False),
    Column("alias_norm", Text, nullable=False),
    PrimaryKeyConstraint("entity_id", "alias_norm"),
    Index("ix_entity_aliases_alias_norm", "alias_norm"),
)
