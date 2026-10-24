from datetime import UTC, datetime
from pathlib import Path

import pytest

from sportintel.modules.ingestion.domain.article import clip_words, html_to_text
from sportintel.modules.ingestion.infrastructure.feeds import FeedParseError, parse_date, parse_feed

FIX = Path(__file__).resolve().parents[3].parent / "fixtures" / "sources" / "default"


def test_rss_all_fields() -> None:
    items = parse_feed(
        (FIX / "rss_ge.xml").read_bytes(), "application/rss+xml", "https://ge.globo.com/"
    )
    assert len(items) == 10
    first = items[0]
    assert first.title.startswith("Flamengo confirma lesão de Pedro")
    assert first.url.startswith("https://ge.globo.com/futebol/times/flamengo/")
    assert first.published_at == datetime(2026, 10, 7, 13, 0, tzinfo=UTC)
    assert first.image_url == "https://s2.glbimg.com/fixture/0.jpg"
    assert first.author == "Redação ge 0"
    assert "<b>" in (first.summary or "")  # сырой summary; HTML вычищается при сохранении


def test_rss_date_without_tz_is_sao_paulo() -> None:
    items = parse_feed(
        (FIX / "rss_ge.xml").read_bytes(), "application/rss+xml", "https://ge.globo.com/"
    )
    vasco = next(i for i in items if "Vasco" in i.title)
    assert vasco.published_at is not None
    assert vasco.published_at.astimezone(UTC) == datetime(2026, 10, 7, 1, 0, tzinfo=UTC)


def test_atom_relative_link_and_missing_title() -> None:
    items = parse_feed(
        (FIX / "atom_sample.xml").read_bytes(), "application/atom+xml", "https://news.example.com/"
    )
    assert [i.title for i in items] == [
        "Internacional anuncia novo patrocinador master",
        "Cruzeiro tem desfalque para a próxima rodada",
    ]
    assert items[1].url == "https://news.example.com/cruzeiro/desfalque"
    assert items[0].author == "Repórter Atom"


def test_sitemap_news() -> None:
    items = parse_feed(
        (FIX / "sitemap_news.xml").read_bytes(), "application/xml", "https://www.lance.com.br/"
    )
    assert [i.title for i in items] == [
        "Fluminense vence e se aproxima do G-4",
        "Santos empata em casa",
    ]
    assert items[0].image_url == "https://www.lance.com.br/img/flu.jpg"
    assert items[0].published_at == datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def test_broken_xml_without_items() -> None:
    with pytest.raises(FeedParseError):
        parse_feed(b"<rss><channel><item><title>x", "application/rss+xml", "https://x.com/")


def test_bozo_feed_with_items_is_used() -> None:
    body = b"<rss><channel><item><title>Ok</title><link>https://x.com/a</link></item>&broken;</channel></rss>"
    assert [i.title for i in parse_feed(body, "application/rss+xml", "https://x.com/")] == ["Ok"]


def test_sitemap_xxe_is_rejected() -> None:
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>&e;</loc></url></urlset>'
    with pytest.raises(FeedParseError):
        parse_feed(evil, "application/xml", "https://x.com/")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "<p>O <b>Flamengo</b> venceu&nbsp;hoje.</p><script>x()</script>",
            "O Flamengo venceu hoje.",
        ),
        ("linha 1<br>linha 2", "linha 1 linha 2"),
        ("sem html", "sem html"),
    ],
)
def test_html_to_text(raw: str, expected: str) -> None:
    assert html_to_text(raw) == expected


def test_clip_words() -> None:
    assert clip_words("um dois tres quatro", 12) == "um dois"
    assert clip_words("curto", 500) == "curto"


@pytest.mark.parametrize("raw", [None, "", "not a date"])
def test_parse_date_garbage(raw: str | None) -> None:
    assert parse_date(raw) is None
