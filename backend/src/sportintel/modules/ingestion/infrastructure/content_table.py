from sqlalchemy import Column, DateTime, ForeignKey, Index, Table, Text
from sqlalchemy.dialects.postgresql import UUID

from sportintel.modules.ingestion.infrastructure.tables import metadata

article_content = Table(
    "article_content",
    metadata,
    Column(
        "article_id",
        UUID(as_uuid=True),
        ForeignKey("ingestion.articles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("text", Text, nullable=False),
    Column("extracted_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Index("ix_article_content_expires_at", "expires_at"),
)
