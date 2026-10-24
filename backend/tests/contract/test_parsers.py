"""Contract-тесты профилей на сохранённых страницах (BE-T1.8): ловят смену вёрстки до прода."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from sportintel.modules.ingestion.infrastructure.parsers import REGISTRY, get_profile
from sportintel.modules.ingestion.jobs import extract_with_profile

FIXTURES = Path(__file__).resolve().parents[2].parent / "fixtures" / "sources"


def _cases(profile: str) -> list[tuple[str, dict]]:
    expected = json.loads((FIXTURES / profile / "expected.json").read_text(encoding="utf-8"))
    return sorted(expected.items())


@pytest.mark.parametrize(("name", "want"), _cases("default"))
def test_default_profile_pages(name: str, want: dict) -> None:
    page = extract_with_profile((FIXTURES / "default" / name).read_bytes(), want["url"], "default")
    assert page.title == want["title"]
    got = page.published_at
    exp = datetime.fromisoformat(want["published_at"]) if want["published_at"] else None
    assert (got.replace(second=0, microsecond=0) if got else None) == (
        exp.replace(second=0, microsecond=0) if exp else None
    )
    assert (page.description or page.text or "")[:50] == want["lead_prefix"]
    assert page.image_url == want["image_url"]


@pytest.mark.parametrize(("name", "want"), _cases("cbf"))
def test_cbf_list_page(name: str, want: dict) -> None:
    items = get_profile("cbf").list_items(
        (FIXTURES / "cbf" / name).read_bytes(),
        "text/html",
        "https://www.cbf.com.br/futebol-brasileiro/noticias",
    )
    assert [i.url for i in items] == want["items"]
    assert all(len(i.title) >= 15 for i in items)


def test_every_registered_profile_has_fixtures() -> None:
    assert {p for p in REGISTRY if (FIXTURES / p / "expected.json").exists()} == set(REGISTRY)


def test_unknown_profile_falls_back_to_default() -> None:
    assert get_profile("nope").name == "default"


@pytest.mark.parametrize(("name", "want"), _cases("telegram"))
def test_telegram_channel_page(name: str, want: dict) -> None:
    items = get_profile("telegram").list_items(
        (FIXTURES / "telegram" / name).read_bytes(), "text/html", want["base_url"]
    )
    assert len(items) == want["count"]
    last = items[-1]
    assert last.url == want["last_url"]
    assert last.title.startswith(want["last_title_prefix"])
    assert last.published_at == datetime.fromisoformat(want["last_published_at"])
    assert all(i.summary and i.summary.startswith(i.title.rstrip("…")) for i in items)


def test_telegram_service_messages_are_not_news() -> None:
    page = (
        b'<div class="tgme_widget_message service_message js-widget_message" data-post="c/1">'
        b'<div class="tgme_widget_message_text">Channel created</div></div>'
        b'<div class="tgme_widget_message js-widget_message" data-post="c/2">'
        b'<div class="tgme_widget_message_text">Flamengo vence</div></div>'
    )
    items = get_profile("telegram").list_items(page, "text/html", "https://t.me/s/c")
    assert [i.title for i in items] == ["Flamengo vence"]


def test_telegram_post_page_text_from_og() -> None:
    page = extract_with_profile(
        (FIXTURES / "telegram" / "post_page.html").read_bytes(),
        "https://t.me/igaming_news/11547",
        "telegram",
    )
    assert (page.text or "").startswith("🦅🔮 В США четыре индейских племени")


HOLIDAY_FEEDS = {
    "holidays_openholidays": "https://openholidaysapi.org/PublicHolidays?countryIsoCode=DE&validFrom=2026-01-01",
    "holidays_govuk": "https://www.gov.uk/bank-holidays.json",
    "holidays_brasilapi": "https://brasilapi.com.br/api/feriados/v1/2026",
    "holidays_ruwiki": "https://ru.wikipedia.org/wiki/x?year=2026",
}


@pytest.mark.parametrize("profile", sorted(HOLIDAY_FEEDS))
def test_holiday_sources(profile: str) -> None:
    for name, want in _cases(profile):
        items = get_profile(profile).list_items(
            (FIXTURES / profile / name).read_bytes(), "application/json", HOLIDAY_FEEDS[profile]
        )
        got = {(i.published_at.date().isoformat(), i.title) for i in items if i.published_at}
        assert len(items) == want["count"]
        assert {tuple(x) for x in want["contains"]} <= got
