"""analytics: view_heartbeats и представления для метрик (BE-T4.15)

Revision ID: 202610091400
Revises: 202610091300
Create Date: 2026-10-09 14:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610091400"
down_revision: str | None = "202610091300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEWS = {
    "v_transitions": """
        SELECT context_event_id AS event_id, actor_id, at, before->>'status' AS from_status, after->>'status' AS to_status,
               after->>'rejection_reason' AS reason
        FROM audit.audit_log WHERE action = 'event.transitioned'""",
    "v_events": """
        SELECT id, status, rejection_reason, relevance, relevance_origin, first_seen_at, origin FROM events.events""",
    "v_activity": """
        SELECT actor_id AS user_id, at FROM audit.audit_log WHERE actor_id IS NOT NULL
        UNION ALL SELECT user_id, at FROM analytics.view_heartbeats""",
    "v_draft_versions": """
        SELECT v.draft_id, d.event_id, v.n, v.origin, v.body_tg_html, v.created_at, d.created_by IS NULL AS auto
        FROM editorial.telegram_draft_versions v JOIN editorial.telegram_drafts d ON d.id = v.draft_id""",
    "v_first_sources": """
        SELECT DISTINCT ON (ea.event_id) ea.event_id, a.source_id, s.name AS source_name
        FROM events.event_articles ea JOIN ingestion.articles a ON a.id = ea.article_id JOIN sources.sources s ON s.id = a.source_id
        WHERE NOT ea.is_duplicate ORDER BY ea.event_id, coalesce(a.published_at, a.discovered_at)""",
}


def upgrade() -> None:
    op.create_table(
        "view_heartbeats",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", pg.UUID(as_uuid=True)),
        sa.Column(
            "at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        schema="analytics",
    )
    op.create_index(
        "ix_view_heartbeats_user_at", "view_heartbeats", ["user_id", "at"], schema="analytics"
    )
    for name, sql in VIEWS.items():
        op.execute(f"CREATE OR REPLACE VIEW analytics.{name} AS {sql}")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app') THEN"
        " GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO app; END IF; END $$"
    )


def downgrade() -> None:
    for name in VIEWS:
        op.execute(f"DROP VIEW IF EXISTS analytics.{name}")
    op.drop_table("view_heartbeats", schema="analytics")
