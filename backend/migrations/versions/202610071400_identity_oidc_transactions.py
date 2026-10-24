"""identity: oidc_transactions

Revision ID: 202610071400
Revises: 202610071300
Create Date: 2026-10-07 14:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610071400"
down_revision: str | None = "202610071300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oidc_transactions",
        sa.Column("tx_id", sa.Text(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("code_verifier", sa.Text(), nullable=False),
        sa.Column("next_path", sa.Text(), nullable=False, server_default="/"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="identity",
    )
    op.create_index(
        "ix_oidc_transactions_created_at", "oidc_transactions", ["created_at"], schema="identity"
    )


def downgrade() -> None:
    op.drop_table("oidc_transactions", schema="identity")
