"""sources: официальные праздники по странам (тип calendar, профиль holidays), без сети

Источник = страна: даты — из официальных календарей python-holidays, ссылка — страница праздников
страны в Википедии. API Nager.Date закрыт для роботов (robots.txt), поэтому не используется.
Calend.ru и Office Holidays выключены: там неофициальные «дни» и дубли одних и тех же праздников.

Revision ID: 202610101200
Revises: 202610101100
Create Date: 2026-10-10 12:00:00+00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610101200"
down_revision: str | None = "202610101100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMESPACE = uuid.UUID("6f1d3a52-0b1e-4c8e-9a51-5e3f3c0a1b01")  # как в 202610071510
WIKI = "https://en.wikipedia.org/wiki/"
COUNTRIES = [
    ("RU", "Россия", "Public_holidays_in_Russia"),
    ("BR", "Бразилия", "Public_holidays_in_Brazil"),
    ("US", "США", "Public_holidays_in_the_United_States"),
    ("GB", "Великобритания", "Public_holidays_in_the_United_Kingdom"),
    ("DE", "Германия", "Public_holidays_in_Germany"),
    ("FR", "Франция", "Public_holidays_in_France"),
    ("ES", "Испания", "Public_holidays_in_Spain"),
    ("IT", "Италия", "Public_holidays_in_Italy"),
    ("PT", "Португалия", "Public_holidays_in_Portugal"),
    ("AR", "Аргентина", "Public_holidays_in_Argentina"),
    ("MX", "Мексика", "Public_holidays_in_Mexico"),
    ("TR", "Турция", "Public_holidays_in_Turkey"),
    ("KZ", "Казахстан", "Public_holidays_in_Kazakhstan"),
    ("BY", "Беларусь", "Public_holidays_in_Belarus"),
    ("UA", "Украина", "Public_holidays_in_Ukraine"),
]
OLD = ["https://www.calend.ru", "https://www.officeholidays.com"]


def _id(base_url: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, base_url)


def upgrade() -> None:
    op.drop_constraint("ck_sources_kind", "sources", schema="sources")
    op.create_check_constraint(
        "ck_sources_kind",
        "sources",
        "kind IN ('rss','sitemap','html','manual','calendar')",
        schema="sources",
    )
    bind = op.get_bind()
    for cc, name, page in COUNTRIES:
        bind.execute(
            sa.text(
                "INSERT INTO sources.sources (id, name, domain, base_url, kind, feed_urls, tier,"
                " owner_group, parser_profile, poll_interval_seconds, language, region,"
                " url_keep_params, next_poll_at)"
                " VALUES (:id, :name, 'en.wikipedia.org', :page, 'calendar', ARRAY[:page],"
                " 'OFFICIAL', 'official_calendar', 'holidays', 21600, 'en', :cc,"
                " ARRAY['holiday'], now()) ON CONFLICT DO NOTHING"
            ),
            dict(id=_id(WIKI + page), name=f"{name} — праздники", page=WIKI + page, cc=cc),
        )
    bind.execute(
        sa.text("UPDATE sources.sources SET active = false WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [str(_id(b)) for b in OLD]},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE sources.sources SET active = true WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [str(_id(b)) for b in OLD]},
    )
    bind.execute(
        sa.text("DELETE FROM sources.sources WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [str(_id(WIKI + p)) for _, _, p in COUNTRIES]},
    )
    op.drop_constraint("ck_sources_kind", "sources", schema="sources")
    op.create_check_constraint(
        "ck_sources_kind", "sources", "kind IN ('rss','sitemap','html','manual')", schema="sources"
    )
