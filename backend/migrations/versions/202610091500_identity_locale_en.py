"""identity: язык интерфейса по умолчанию — en (UI переключается между en и ru)

Revision ID: 202610091500
Revises: 202610091400
Create Date: 2026-10-09 15:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202610091500"
down_revision: str | None = "202610091400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "locale", server_default="en", schema="identity")
    # pt-BR больше не предлагается в UI: профили с прежним дефолтом переводим на en.
    op.execute("UPDATE identity.users SET locale = 'en' WHERE locale = 'pt-BR'")


def downgrade() -> None:
    op.alter_column("users", "locale", server_default="pt-BR", schema="identity")
