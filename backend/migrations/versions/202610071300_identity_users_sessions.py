"""identity: users, sessions

Revision ID: 202610071300
Revises: 202610071200
Create Date: 2026-10-07 13:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610071300"
down_revision: str | None = "202610071200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("role", sa.Text(), nullable=False, server_default="researcher"),
        sa.Column("locale", sa.Text(), nullable=False, server_default="pt-BR"),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="America/Sao_Paulo"),
        sa.Column("hotkeys_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("invited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("oidc_subject", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint("role IN ('researcher','editor','admin')", name="ck_users_role"),
        sa.CheckConstraint("locale IN ('pt-BR','en','ru')", name="ck_users_locale"),
        sa.UniqueConstraint("email", name="ux_users_email"),
        sa.UniqueConstraint("oidc_subject", name="ux_users_oidc_subject"),
        schema="identity",
    )
    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.LargeBinary(), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("csrf_token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", pg.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        schema="identity",
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema="identity")
    op.create_index(
        "ix_sessions_absolute_expires_at", "sessions", ["absolute_expires_at"], schema="identity"
    )


def downgrade() -> None:
    op.drop_table("sessions", schema="identity")
    op.drop_table("users", schema="identity")
