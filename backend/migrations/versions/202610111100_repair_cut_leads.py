"""Лиды, обрезанные лентой («…сосредоточит...»), — из текста статьи; сводки событий на их основе тоже

Лента (например, Calend.ru) отдаёт описание, оборванное на полуслове; теперь extract_article
в таком случае берёт лид из текста статьи. Здесь — то же для уже собранных статей.

Revision ID: 202610111100
Revises: 202610111000
Create Date: 2026-10-11 11:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from sportintel.modules.ingestion.application.extract_article import cut_off, lead_from_text

revision: str = "202610111100"
down_revision: str | None = "202610111000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT a.id, a.lead, c.text FROM ingestion.articles a"
            " JOIN ingestion.article_content c ON c.article_id = a.id WHERE a.lead IS NOT NULL"
        )
    )
    for article_id, old, text in rows.fetchall():
        if not cut_off(old) or not text.strip():
            continue
        new = lead_from_text(text)
        bind.execute(
            sa.text("UPDATE ingestion.articles SET lead = :n WHERE id = :i"),
            {"n": new, "i": article_id},
        )
        bind.execute(
            sa.text(
                "UPDATE events.events SET summary = :n"
                " WHERE summary = :o AND summary_origin = 'source'"
            ),
            {"n": new, "o": old},
        )


def downgrade() -> None:
    pass  # обрезанные лиды не восстанавливаем
