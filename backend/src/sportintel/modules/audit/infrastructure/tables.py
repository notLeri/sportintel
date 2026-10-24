from sqlalchemy import BigInteger, Column, DateTime, Identity, MetaData, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from sportintel.platform.db_metadata import register

metadata = register(MetaData(schema="audit"))

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("actor_id", UUID(as_uuid=True)),
    Column("action", Text, nullable=False),
    Column("target_type", Text, nullable=False),
    Column("target_id", Text, nullable=False),
    Column("before", JSONB),
    Column("after", JSONB),
    Column("reason", Text),
    Column("request_id", Text),
    Column("context_event_id", UUID(as_uuid=True)),
)
