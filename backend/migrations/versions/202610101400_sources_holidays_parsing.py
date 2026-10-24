"""sources: официальные праздники только парсингом (OpenHolidays, GOV.UK, BrasilAPI, Википедия)

Календари python-holidays (202610101200) выключены: данные — только из источников, которые мы парсим.
У уже собранных праздников content_hash заменяется отпечатком «страна + дата + регионы»
(как ingestion.domain.holiday.fingerprint): тот же праздник с нового сайта станет перепечаткой.

Revision ID: 202610101400
Revises: 202610101300
Create Date: 2026-10-10 14:00:00+00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610101400"
down_revision: str | None = "202610101300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMESPACE = uuid.UUID("6f1d3a52-0b1e-4c8e-9a51-5e3f3c0a1b01")  # как в 202610071510
OH = "https://openholidaysapi.org/PublicHolidays?countryIsoCode={cc}"
OH_FEED = OH + "&validFrom={{year}}-01-01&validTo={{year}}-12-31&languageIsoCode=EN"
# «Праздники России»: КонсультантПлюс закрыт для ботов (HTTP 428), в статье — список ст. 112 ТК РФ.
RU_WIKI = (
    "https://ru.wikipedia.org/wiki/"
    "%D0%9F%D1%80%D0%B0%D0%B7%D0%B4%D0%BD%D0%B8%D0%BA%D0%B8_%D0%A0%D0%BE%D1%81%D1%81%D0%B8%D0%B8"
)
OH_COUNTRIES = [
    ("DE", "Германия"), ("FR", "Франция"), ("ES", "Испания"), ("IT", "Италия"),
    ("PT", "Португалия"), ("MX", "Мексика"), ("BY", "Беларусь"), ("BR", "Бразилия"),
]  # fmt: skip
# name, domain, base_url, feed_url, tier, owner_group, profile, language, region, keep_params
SOURCES = [
    *(
        (f"OpenHolidays — {name}", "openholidaysapi.org", OH.format(cc=cc), OH_FEED.format(cc=cc),
         "A", "openholidays", "holidays_openholidays", "en", cc, ["countryIsoCode", "holiday"])
        for cc, name in OH_COUNTRIES
    ),
    ("GOV.UK — праздники Великобритании", "www.gov.uk", "https://www.gov.uk/bank-holidays",
     "https://www.gov.uk/bank-holidays.json", "OFFICIAL", "gov_uk", "holidays_govuk", "en", "GB",
     ["holiday"]),
    ("BrasilAPI — праздники Бразилии", "brasilapi.com.br", "https://brasilapi.com.br/api/feriados",
     "https://brasilapi.com.br/api/feriados/v1/{year}", "B", "brasilapi", "holidays_brasilapi",
     "pt-BR", "BR", ["holiday"]),
    ("Википедия — праздники России", "ru.wikipedia.org", RU_WIKI, RU_WIKI + "?year={year}", "B",
     "wikipedia", "holidays_ruwiki", "ru", "RU", ["holiday"]),
]  # fmt: skip

FINGERPRINT_SQL = """
UPDATE ingestion.articles a SET content_hash = (
  'x' || substr(encode(sha256(convert_to(
    'holiday|' || s.region || '|' || coalesce(substring(a.lead from 'Date: (\\d{4}-\\d{2}-\\d{2})'),
                                              to_char(a.published_at, 'YYYY-MM-DD'))
    || '|' || coalesce(substring(a.title from '\\(([A-Z]{2}-[A-Z0-9-]+(?:, [A-Z]{2}-[A-Z0-9-]+)*)\\)$'),
                       'national'),
  'UTF8')), 'hex'), 1, 16))::bit(64)::bigint
FROM sources.sources s
WHERE s.id = a.source_id AND s.parser_profile = 'holidays' AND a.duplicate_of IS NULL
"""


def _id(base_url: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, base_url)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(FINGERPRINT_SQL))
    bind.execute(
        sa.text("UPDATE sources.sources SET active = false WHERE parser_profile = 'holidays'")
    )
    for name, domain, base, feed, tier, owner, profile, lang, region, keep in SOURCES:
        bind.execute(
            sa.text(
                "INSERT INTO sources.sources (id, name, domain, base_url, kind, feed_urls, tier,"
                " owner_group, parser_profile, poll_interval_seconds, language, region,"
                " url_keep_params, next_poll_at)"
                " VALUES (:id, :name, :domain, :base, 'calendar', ARRAY[:feed], :tier, :owner,"
                " :profile, 21600, :lang, :region, CAST(:keep AS text[]), now())"
                " ON CONFLICT DO NOTHING"
            ),
            dict(id=_id(base), name=name, domain=domain, base=base, feed=feed, tier=tier,
                 owner=owner, profile=profile, lang=lang, region=region, keep=keep),
        )  # fmt: skip


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM sources.sources WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [str(_id(s[2])) for s in SOURCES]},
    )
    bind.execute(
        sa.text("UPDATE sources.sources SET active = true WHERE parser_profile = 'holidays'")
    )
