"""editorial: telegram_drafts, telegram_draft_versions

Revision ID: 202610091100
Revises: 202610091000
Create Date: 2026-10-09 11:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610091100"
down_revision: str | None = "202610091000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
U = pg.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "telegram_drafts",
        sa.Column("id", U, primary_key=True),
        sa.Column(
            "event_id",
            U,
            sa.ForeignKey("events.events.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.Text()),
        sa.Column("created_by", U),
        sa.Column("auto_basis_hash", sa.Text()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "state IN ('generating','ready','failed')", name="ck_telegram_drafts_state"
        ),
        schema="editorial",
    )
    op.create_table(
        "telegram_draft_versions",
        sa.Column(
            "draft_id",
            U,
            sa.ForeignKey("editorial.telegram_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("body_tg_html", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text()),
        sa.Column("disclaimer_kinds", pg.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("disclaimer_removed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("citations", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("grounding_report", pg.JSONB()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("ai_run_id", U),
        sa.Column("author_id", U),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.PrimaryKeyConstraint("draft_id", "n"),
        sa.CheckConstraint(
            "origin IN ('ai','human','template')", name="ck_telegram_draft_versions_origin"
        ),
        schema="editorial",
    )


def downgrade() -> None:
    op.drop_table("telegram_draft_versions", schema="editorial")
    op.drop_table("telegram_drafts", schema="editorial")
