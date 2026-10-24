"""identity.users.password_hash — вход по паролю без внешнего IdP

Revision ID: 202610121000
Revises: 202610111600
Create Date: 2026-10-12 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610121000"
down_revision: str | None = "202610111600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # expand: колонка необязательная, прежний код её не читает
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True), schema="identity")


def downgrade() -> None:
    op.drop_column("users", "password_hash", schema="identity")
