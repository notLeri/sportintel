from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Table, Text
from sqlalchemy.dialects.postgresql import UUID

from sportintel.modules.sources.infrastructure.tables import metadata

fetch_runs = Table(
    "fetch_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "source_id",
        UUID(as_uuid=True),
        ForeignKey("sources.sources.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("feed_url", Text, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("status", Text, nullable=False),
    Column("http_status", Integer, nullable=True),
    Column("items_seen", Integer, nullable=False, server_default="0"),
    Column("items_new", Integer, nullable=False, server_default="0"),
    Column("error_code", Text, nullable=True),
    Column("error_detail", Text, nullable=True),
    CheckConstraint(
        "status IN ('ok','not_modified','error','skipped')", name="ck_fetch_runs_status"
    ),
    Index("ix_fetch_runs_source_id_started_at", "source_id", "started_at"),
)
