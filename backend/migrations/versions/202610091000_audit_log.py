"""audit: audit_log (append-only)

Revision ID: 202610091000
Revises: 202610081500
Create Date: 2026-10-09 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610091000"
down_revision: str | None = "202610081500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("actor_id", pg.UUID(as_uuid=True)),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("before", pg.JSONB()),
        sa.Column("after", pg.JSONB()),
        sa.Column("reason", sa.Text()),
        sa.Column("request_id", sa.Text()),
        sa.Column("context_event_id", pg.UUID(as_uuid=True)),
        schema="audit",
    )
    for name, cols in {
        "ix_audit_log_context_event": "context_event_id, at DESC",
        "ix_audit_log_target": "target_type, target_id, at DESC",
        "ix_audit_log_actor_at": "actor_id, at DESC",
        "ix_audit_log_action_at": "action, at DESC",
    }.items():
        op.execute(f"CREATE INDEX {name} ON audit.audit_log ({cols})")
    # Append-only на уровне прав; в local/CI роли app может не быть.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app') THEN"
        " REVOKE UPDATE, DELETE, TRUNCATE ON audit.audit_log FROM app;"
        " ELSE RAISE NOTICE 'role app not found: REVOKE skipped'; END IF; END $$"
    )


def downgrade() -> None:
    op.drop_table("audit_log", schema="audit")
