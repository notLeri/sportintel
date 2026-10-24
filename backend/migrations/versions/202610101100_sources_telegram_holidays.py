"""sources: несколько источников на домен (Telegram-каналы на t.me), каналы и праздники

Revision ID: 202610101100
Revises: 202610101000
Create Date: 2026-10-10 11:00:00+00:00
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610101100"
down_revision: str | None = "202610101000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMESPACE = uuid.UUID("6f1d3a52-0b1e-4c8e-9a51-5e3f3c0a1b01")  # как в 202610071510
# name, domain, base_url, kind, feed_url, tier, owner_group, profile, poll_s, language, region
SOURCES = [
    ("iGamingNews (Telegram)", "t.me", "https://t.me/igaming_news", "html",
     "https://t.me/s/igaming_news", "C", "tg_igaming_news", "telegram", 900, "ru", "RU"),
    ("Матч ТВ (Telegram)", "t.me", "https://t.me/Match_TV", "html",
     "https://t.me/s/Match_TV", "B", "match_tv", "telegram", 600, "ru", "RU"),
    ("Winline (Telegram)", "t.me", "https://t.me/winline", "html",
     "https://t.me/s/winline", "C", "winline", "telegram", 900, "ru", "RU"),
    ("Daily iGaming (Telegram)", "t.me", "https://t.me/DailyiGamingEN", "html",
     "https://t.me/s/DailyiGamingEN", "C", "tg_daily_igaming", "telegram", 900, "en", "ZZ"),
    ("Calend.ru — праздники", "calend.ru", "https://www.calend.ru", "rss",
     "https://www.calend.ru/rss/today-holidays.rss", "B", "calend_ru", "default", 21600, "ru", "RU"),
    ("Office Holidays", "officeholidays.com", "https://www.officeholidays.com", "rss",
     "https://www.officeholidays.com/rss/all_holidays", "B", "officeholidays", "default", 21600,
     "en", "ZZ"),
]  # fmt: skip
SPORTS = [
    ("hockey", {"pt-BR": "Hóquei", "en": "Hockey", "ru": "Хоккей"}, 70),
    ("igaming", {"pt-BR": "iGaming", "en": "iGaming", "ru": "iGaming"}, 80),
    ("holidays", {"pt-BR": "Feriados", "en": "Holidays", "ru": "Праздники"}, 90),
]


def _id(base_url: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, base_url)


def upgrade() -> None:
    op.drop_constraint("sources_domain_key", "sources", schema="sources")
    op.create_unique_constraint(
        "sources_domain_base_url_key", "sources", ["domain", "base_url"], schema="sources"
    )
    for name, domain, base, kind, feed, tier, owner, profile, poll, lang, region in SOURCES:
        op.get_bind().execute(
            sa.text(
                "INSERT INTO sources.sources (id, name, domain, base_url, kind, feed_urls, tier,"
                " owner_group, parser_profile, poll_interval_seconds, language, region)"
                " VALUES (:id, :name, :domain, :base, :kind, ARRAY[:feed], :tier, :owner,"
                " :profile, :poll, :lang, :region) ON CONFLICT DO NOTHING"
            ),
            dict(id=_id(base), name=name, domain=domain, base=base, kind=kind, feed=feed,
                 tier=tier, owner=owner, profile=profile, poll=poll, lang=lang, region=region),
        )  # fmt: skip
    for sid, names, sort in SPORTS:
        op.get_bind().execute(
            sa.text(
                "INSERT INTO taxonomy.sports (id, name_i18n, sort)"
                " VALUES (:id, CAST(:n AS jsonb), :s) ON CONFLICT DO NOTHING"
            ),
            {"id": sid, "n": json.dumps(names, ensure_ascii=False), "s": sort},
        )


def downgrade() -> None:
    ids = [str(_id(s[2])) for s in SOURCES]
    op.get_bind().execute(
        sa.text("DELETE FROM sources.sources WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": ids}
    )
    op.drop_constraint("sources_domain_base_url_key", "sources", schema="sources")
    op.create_unique_constraint("sources_domain_key", "sources", ["domain"], schema="sources")
