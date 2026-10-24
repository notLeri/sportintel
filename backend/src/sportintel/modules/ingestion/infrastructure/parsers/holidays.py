"""Официальные праздники — парсинг открытых источников (robots.txt разрешает):

- holidays_openholidays — OpenHolidays API (ЕС, Мексика, Беларусь…; региональные — коды ISO 3166-2);
- holidays_govuk — GOV.UK bank-holidays.json (Великобритания по частям страны);
- holidays_brasilapi — BrasilAPI /feriados (национальные праздники Бразилии);
- holidays_ruwiki — «Праздники России» в Википедии (нерабочие дни по ст. 112 ТК РФ;
  КонсультантПлюс закрыт для ботов — HTTP 428).

Все профили отдают элементы одного вида (holiday_item): заголовок «Название (регионы)», дата —
published_at. По ним ingestion считает отпечаток «страна + дата + регионы» (domain.holiday) — один и тот
же праздник из разных источников становится перепечаткой одного события, а не новым событием.
В адресах лент {year} подставляет fetch_source; в ленту попадают только ближайшие LEAD_DAYS дней.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from html import unescape

from sportintel.modules.ingestion.domain.feed_item import FeedItem
from sportintel.modules.ingestion.infrastructure.extractor import ExtractedPage

# ponytail: константа; в настройки — если редакции понадобится другой горизонт
LEAD_DAYS = 3


def holiday_item(page: str, day: date, name: str, country: str, regions: list[str]) -> FeedItem:
    """Единый вид праздника для всех источников (на нём держится дедупликация)."""
    scope = ", ".join(sorted(set(regions)))
    where = f"{country}: {scope}" if scope else country
    kind = "regional public holiday" if scope else "official public holiday"
    key = f"{day.isoformat()}-{hashlib.sha256(f'{name}|{scope}'.encode()).hexdigest()[:10]}"
    sep = "&" if "?" in page else "?"
    return FeedItem(
        url=f"{page}{sep}holiday={key}",
        title=f"{name} ({scope})" if scope else name,
        summary=f"{name} — {kind}, {where}. Date: {day.isoformat()}.",
        published_at=datetime(day.year, day.month, day.day, tzinfo=UTC),
        image_url=None,
        author=None,
    )


@dataclass(frozen=True)
class _Base:
    name: str
    empty_list_is_error: bool = False  # в ближайшие дни праздников может не быть
    max_lead: timedelta = field(default=timedelta(days=LEAD_DAYS))

    def postprocess(self, page: ExtractedPage, html: bytes, url: str) -> ExtractedPage:
        return page  # страница праздника не скачивается: текст уже в ленте


class OpenHolidaysProfile(_Base):
    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
        country = re.search(r"countryIsoCode=([A-Z]{2})", base_url)
        cc = country.group(1) if country else "ZZ"
        items = []
        for h in json.loads(body):
            if h.get("type") != "Public":
                continue
            names = {n["language"]: n["text"] for n in h["name"]}
            name = names.get("EN") or next(iter(names.values()))
            regions = [] if h.get("nationwide") else [s["code"] for s in h.get("subdivisions", [])]
            items.append(
                holiday_item(base_url, date.fromisoformat(h["startDate"]), name, cc, regions)
            )
        return items


GOVUK_REGIONS = {
    "england-and-wales": ["GB-ENG", "GB-WLS"],
    "scotland": ["GB-SCT"],
    "northern-ireland": ["GB-NIR"],
}


class GovUkProfile(_Base):
    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
        where: dict[tuple[str, str], list[str]] = {}
        for division, data in json.loads(body).items():
            for e in data.get("events", []):
                where.setdefault((e["date"], e["title"]), []).extend(GOVUK_REGIONS[division])
        everywhere = sorted(r for rs in GOVUK_REGIONS.values() for r in rs)
        return [
            holiday_item(
                base_url,
                date.fromisoformat(d),
                title,
                "GB",
                [] if sorted(regions) == everywhere else regions,
            )
            for (d, title), regions in sorted(where.items())
        ]


class BrasilApiProfile(_Base):
    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
        return [
            holiday_item(base_url, date.fromisoformat(h["date"]), h["name"], "BR", [])
            for h in json.loads(body)
            if h.get("type") == "national"
        ]


_RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}  # fmt: skip
_RU_SECTION = re.compile(r"Всего их[^<]*</p>\s*<ul[^>]*>(.*?)</ul>", re.S)
_RU_ITEM = re.compile(r"([\d,\s—–-]+)\s+(" + "|".join(_RU_MONTHS) + r")\s+—\s+(.+)")


def _ru_days(spec: str) -> list[int]:
    """«1—6, 8» → [1, 2, 3, 4, 5, 6, 8]."""
    days: list[int] = []
    for part in re.split(r",\s*", spec.strip()):
        bounds = [int(x) for x in re.split(r"\s*[—–-]\s*", part) if x]
        days += list(range(bounds[0], bounds[-1] + 1))
    return days


class RuWikiProfile(_Base):
    """«Праздники России» в Википедии: нерабочие праздничные дни по ст. 112 ТК РФ.

    Год — параметр year в адресе ленты (?year={year}): в статье список без года."""

    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
        year = re.search(r"[?&]year=(\d{4})", base_url)
        section = _RU_SECTION.search(body.decode("utf-8", "replace"))
        if not year or not section:
            raise ValueError("holiday list not found (layout changed?)")
        items = []
        for li in re.findall(r"<li[^>]*>(.*?)</li>", section.group(1), re.S):
            text = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", li))).strip()
            m = _RU_ITEM.match(text)
            if not m:
                continue
            for d in _ru_days(m.group(1)):
                day = date(int(year.group(1)), _RU_MONTHS[m.group(2)], d)
                items.append(holiday_item(base_url, day, m.group(3).strip(), "RU", []))
        return items


OPENHOLIDAYS = OpenHolidaysProfile("holidays_openholidays")
GOVUK = GovUkProfile("holidays_govuk")
BRASILAPI = BrasilApiProfile("holidays_brasilapi")
RUWIKI = RuWikiProfile("holidays_ruwiki")
HOLIDAY_PROFILES = (OPENHOLIDAYS, GOVUK, BRASILAPI, RUWIKI)
