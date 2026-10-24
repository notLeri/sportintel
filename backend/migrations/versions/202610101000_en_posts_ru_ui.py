"""Язык по умолчанию: интерфейс — ru, посты — en

Revision ID: 202610101000
Revises: 202610092000
Create Date: 2026-10-10 10:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202610101000"
down_revision: str | None = "202610092000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "locale", server_default="ru", schema="identity")
    # en был дефолтом (202610091500), выбор пользователя от дефолта не отличить — переводим всех.
    op.execute("UPDATE identity.users SET locale = 'ru' WHERE locale = 'en'")
    op.execute(
        "UPDATE platform.app_settings"
        " SET value = jsonb_set(value, '{telegram_language}', '\"en\"')"
        " WHERE key = 'languages'"
    )


def downgrade() -> None:
    op.alter_column("users", "locale", server_default="en", schema="identity")
