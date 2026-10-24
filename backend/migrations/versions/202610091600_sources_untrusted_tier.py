"""sources: уровень UNTRUSTED — источник собирается, но не подтверждает события

Revision ID: 202610091600
Revises: 202610091500
Create Date: 2026-10-09 16:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202610091600"
down_revision: str | None = "202610091500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_sources_tier", "sources", schema="sources")
    op.create_check_constraint(
        "ck_sources_tier",
        "sources",
        "tier IN ('OFFICIAL','A','B','C','UNTRUSTED')",
        schema="sources",
    )


def downgrade() -> None:
    op.execute("UPDATE sources.sources SET tier = 'C' WHERE tier = 'UNTRUSTED'")
    op.drop_constraint("ck_sources_tier", "sources", schema="sources")
    op.create_check_constraint(
        "ck_sources_tier", "sources", "tier IN ('OFFICIAL','A','B','C')", schema="sources"
    )
