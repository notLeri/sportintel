from datetime import UTC, datetime

import pytest

from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database
from sportintel.platform.safe_fetch import FakeHttpFetcher, FetchError, FetchRequest, PoliteFetcher
from sportintel.platform.safe_fetch.fake import ok

T0 = datetime(2026, 10, 7, 12, tzinfo=UTC)
FEED = "https://news.example.com/feed.xml"


def polite(db: Database, robots: str | None) -> tuple[PoliteFetcher, FrozenClock, list[float]]:
    routes = {FEED: ok(FEED, "<rss/>"), "https://news.example.com/blocked/x": ok("x", "<html/>")}
    if robots is not None:
        routes["https://news.example.com/robots.txt"] = ok("r", robots, "text/plain")
    clock, slept = FrozenClock(T0), []

    async def fake_sleep(seconds: float) -> None:
        slept.append(round(seconds, 3))
        clock.advance(seconds)

    return PoliteFetcher(FakeHttpFetcher(routes), db, clock, sleep=fake_sleep), clock, slept


async def test_second_request_waits_for_gap(db: Database) -> None:
    f, clock, slept = polite(db, None)
    await f.fetch(FetchRequest(FEED, "feed"), min_gap_ms=2000)
    clock.advance(0.5)
    await f.fetch(FetchRequest(FEED, "feed"), min_gap_ms=2000)
    assert slept == [1.5]


async def test_robots_disallow_and_404_allows(db: Database) -> None:
    f, _, _ = polite(db, "User-agent: SportIntelBot\nDisallow: /blocked/\n")
    with pytest.raises(FetchError) as e:
        await f.fetch(FetchRequest("https://news.example.com/blocked/x", "html"), min_gap_ms=500)
    assert (e.value.code, e.value.permanent) == ("blocked_by_robots", True)
    await f.fetch(FetchRequest(FEED, "feed"), min_gap_ms=500)  # остальное разрешено

    missing, _, _ = polite(db, None)  # robots.txt нет (404) → всё разрешено
    assert (await missing.fetch(FetchRequest(FEED, "feed"), min_gap_ms=500)).status == 200


async def test_crawl_delay_raises_gap(db: Database) -> None:
    f, _, slept = polite(db, "User-agent: *\nCrawl-delay: 5\n")
    await f.fetch(FetchRequest(FEED, "feed"), min_gap_ms=2000)
    await f.fetch(FetchRequest(FEED, "feed"), min_gap_ms=2000)
    assert slept == [5.0]


async def test_robots_cached(db: Database) -> None:
    f, _, _ = polite(db, "User-agent: *\nAllow: /\n")
    inner = f.inner
    assert isinstance(inner, FakeHttpFetcher)
    for _ in range(3):
        await f.fetch(FetchRequest(FEED, "feed"), min_gap_ms=500)
    assert [r.url for r in inner.requests].count("https://news.example.com/robots.txt") == 1


async def test_min_gap_validated(db: Database) -> None:
    f, _, _ = polite(db, None)
    with pytest.raises(ValueError, match="min_gap_ms"):
        await f.fetch(FetchRequest(FEED, "feed"), min_gap_ms=100)
