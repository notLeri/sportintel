from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID

from sportintel.platform.db_metadata import register

metadata = register(MetaData(schema="identity"))
NOW = text("now()")

users = Table(
    "users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("email", CITEXT, nullable=False, unique=True),
    Column("display_name", Text, nullable=False, server_default=""),
    Column("role", Text, nullable=False, server_default="researcher"),
    Column("locale", Text, nullable=False, server_default="ru"),
    Column("timezone", Text, nullable=False, server_default="America/Sao_Paulo"),
    Column("hotkeys_enabled", Boolean, nullable=False, server_default=text("true")),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("invited", Boolean, nullable=False, server_default=text("false")),
    Column("oidc_subject", Text, nullable=True, unique=True),
    Column("password_hash", Text, nullable=True),  # вход по паролю; NULL — пароль не задан
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("role IN ('researcher','editor','admin')", name="ck_users_role"),
    CheckConstraint("locale IN ('pt-BR','en','ru')", name="ck_users_locale"),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id_hash", LargeBinary, primary_key=True),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("csrf_token", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("idle_expires_at", DateTime(timezone=True), nullable=False),
    Column("absolute_expires_at", DateTime(timezone=True), nullable=False),
    Column("ip", INET, nullable=True),
    Column("user_agent", Text, nullable=True),
    Index("ix_sessions_user_id", "user_id"),
    Index("ix_sessions_absolute_expires_at", "absolute_expires_at"),
)

oidc_transactions = Table(
    "oidc_transactions",
    metadata,
    Column("tx_id", Text, primary_key=True),
    Column("state", Text, nullable=False),
    Column("nonce", Text, nullable=False),
    Column("code_verifier", Text, nullable=False),
    Column("next_path", Text, nullable=False, server_default="/"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Index("ix_oidc_transactions_created_at", "created_at"),
)
