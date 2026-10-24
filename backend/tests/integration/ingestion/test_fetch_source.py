from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from tests.factories import make_source

from sportintel.modules.ingestion.application.fetch_source import fetch_source
from sportintel.modules.ingestion.infrastructure.parsers import get_profile
from sportintel.modules.ingestion.infrastructure.repository import SqlArticleRepository
from sportintel.modules.sources.jobs import schedule_due_now
from sportintel.platform import jobs
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database
from sportintel.platform.safe_fetch import FakeHttpFetcher, FetchError, PoliteFetcher
from sportintel.platform.safe_fetch.fake import ok

pytestmark = pytest.mark.integration_commit
FIX = Path(__file__).resolve().parents[3].parent / "fixtures" / "sources" / "default"
FEED = "https://ge.globo.com/rss/fixture/"
NOW = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


async def _noop_sleep(_: float) -> None:
    return None


@pytest.fixture
async def env(
    committing_db: Database,
) -> AsyncIterator[tuple[Database, FakeHttpFetcher, FrozenClock]]:
    async with committing_db.uow() as u:
        await u.session.execute(text("UPDATE sources.sources SET active = false"))
    fake, clock = FakeHttpFetcher(), FrozenClock(NOW)
    yield committing_db, fake, clock
    async with committing_db.uow() as u:
        await u.session.execute(text("DELETE FROM ingestion.articles"))
        await u.session.execute(
            text(
                "DELETE FROM sources.sources WHERE domain LIKE '%.example.com' OR domain = 'fixture.globo.com'"
            )
        )
        await u.session.execute(text("UPDATE sources.sources SET active = true"))


def polite(db: Database, fake: FakeHttpFetcher, clock: FrozenClock) -> PoliteFetcher:
    return PoliteFetcher(fake, db, clock, sleep=_noop_sleep)


async def run(db: Database, fake: FakeHttpFetcher, clock: FrozenClock, source_id):  # type: ignore[no-untyped-def]
    return await fetch_source(
        db,
        lambda u: SqlArticleRepository(u.session),
        source_id,
        polite(db, fake, clock),
        clock,
        get_profile,
    )


async def count(db: Database, sql: str) -> int:
    async with db.uow() as u:
        return (await u.session.execute(text(sql))).scalar_one()


async def test_new_items_become_articles_and_extract_jobs(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    # Источник с доменом globo.com: элементы ge.globo.com — его поддомен.
    async with db.uow() as u:
        await u.session.execute(text("DELETE FROM ingestion.articles"))
        await u.session.execute(text("DELETE FROM sources.sources WHERE domain = 'globo.com'"))
        source = await make_source(
            u,
            domain="globo.com",
            base_url="https://ge.globo.com",
            feed_urls=[FEED],
            min_request_gap_ms=500,
        )
    fake.routes[FEED] = ok(FEED, (FIX / "rss_ge.xml").read_bytes(), etag='"e1"')

    summary = await run(db, fake, clock, source.id)
    assert (summary.ok, summary.items_seen, summary.items_new) == (1, 10, 10)
    assert await count(db, "SELECT count(*) FROM ingestion.articles WHERE state='discovered'") == 10
    assert (
        await count(
            db,
            "SELECT count(*) FROM procrastinate.procrastinate_jobs WHERE task_name='ingestion.extract_article'",
        )
        == 10
    )
    # utm_* срезан канонизацией
    assert (
        await count(db, "SELECT count(*) FROM ingestion.articles WHERE canonical_url LIKE '%utm_%'")
        == 0
    )
    assert await count(db, "SELECT count(*) FROM ingestion.articles WHERE lead LIKE '%<b>%'") == 0

    again = await run(db, fake, clock, source.id)
    assert (again.items_seen, again.items_new) == (10, 0)
    assert fake.requests[-1].etag == '"e1"'  # conditional GET из feed_cache

    async with db.uow() as u:
        runs = (
            await u.session.execute(
                text(
                    "SELECT status, items_new FROM sources.fetch_runs WHERE source_id = :s ORDER BY started_at"
                ),
                {"s": source.id},
            )
        ).all()
        last_new = (
            await u.session.execute(
                text("SELECT last_new_article_at FROM sources.sources WHERE id = :s"),
                {"s": source.id},
            )
        ).scalar()
    assert [tuple(r) for r in runs] == [("ok", 10), ("ok", 0)]
    assert last_new == NOW
    async with db.uow() as u:
        await u.session.execute(text("DELETE FROM ingestion.articles"))
        await u.session.execute(text("DELETE FROM sources.sources WHERE domain = 'globo.com'"))


async def test_not_modified(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(
            u, domain="nm.example.com", feed_urls=["https://nm.example.com/feed"]
        )
    fake.routes["https://nm.example.com/feed"] = ok(
        "https://nm.example.com/feed", b"", not_modified=True, status=304
    )
    summary = await run(db, fake, clock, source.id)
    assert (summary.not_modified, summary.items_new) == (1, 0)
    assert (
        await count(
            db,
            f"SELECT count(*) FROM sources.fetch_runs WHERE source_id='{source.id}' AND status='not_modified'",
        )
        == 1
    )


async def test_transient_error_recorded_then_raised(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(
            u, domain="down.example.com", feed_urls=["https://down.example.com/feed"]
        )
    fake.routes["https://down.example.com/feed"] = FetchError(
        "fetch_http_5xx", "HTTP 503", permanent=False
    )
    with pytest.raises(jobs.TransientError):
        await run(db, fake, clock, source.id)
    assert (
        await count(
            db,
            f"SELECT count(*) FROM sources.fetch_runs WHERE source_id='{source.id}' AND status='error' AND error_code='fetch_http_5xx'",
        )
        == 1
    )
    assert (
        await count(db, f"SELECT consecutive_failures FROM sources.sources WHERE id='{source.id}'")
        == 1
    )


async def test_permanent_error_not_raised(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(
            u, domain="gone.example.com", feed_urls=["https://gone.example.com/feed"]
        )
    summary = await run(db, fake, clock, source.id)  # неизвестный URL у fake → 404 permanent
    assert summary.error_codes == ["fetch_http_4xx"]


async def test_foreign_and_old_items_skipped(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(
            u, domain="mine.example.com", feed_urls=["https://mine.example.com/feed"]
        )
    rss = b"""<rss><channel>
      <item><title>Mine</title><link>https://mine.example.com/a</link><pubDate>Wed, 07 Oct 2026 10:00:00 -0300</pubDate></item>
      <item><title>Foreign</title><link>https://evil.com/b</link></item>
      <item><title>Old</title><link>https://mine.example.com/old</link><pubDate>Mon, 21 Sep 2026 10:00:00 -0300</pubDate></item>
      <item><title>Future</title><link>https://www.mine.example.com/future</link><pubDate>Fri, 09 Oct 2026 10:00:00 -0300</pubDate></item>
    </channel></rss>"""
    fake.routes["https://mine.example.com/feed"] = ok("https://mine.example.com/feed", rss)
    summary = await run(db, fake, clock, source.id)
    assert (summary.items_seen, summary.items_new) == (4, 2)
    async with db.uow() as u:
        future = (
            await u.session.execute(
                text("SELECT published_at FROM ingestion.articles WHERE title='Future'")
            )
        ).scalar()
    assert future is None


async def test_schedule_due_enqueues_only_due_sources(env) -> None:  # type: ignore[no-untyped-def]
    db, _, clock = env
    from datetime import timedelta

    async with db.uow() as u:
        due = await make_source(
            u, domain="due.example.com", next_poll_at=NOW - timedelta(minutes=1)
        )
        await make_source(u, domain="later.example.com", next_poll_at=NOW + timedelta(hours=1))
    jobs.set_runtime(db, clock)
    assert await schedule_due_now() == 1
    async with db.uow() as u:
        args = (
            (
                await u.session.execute(
                    text(
                        "SELECT args FROM procrastinate.procrastinate_jobs WHERE task_name='ingestion.fetch_source'"
                    )
                )
            )
            .scalars()
            .all()
        )
        nxt = (
            await u.session.execute(
                text("SELECT next_poll_at FROM sources.sources WHERE id=:i"), {"i": due.id}
            )
        ).scalar()
    assert [a["source_id"] for a in args] == [str(due.id)]
    assert nxt > NOW


async def test_html_source_with_cbf_profile(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    from sportintel.modules.sources.domain.values import SourceKind

    list_url = "https://www.cbf.example.com/futebol-brasileiro/noticias"
    async with db.uow() as u:
        source = await make_source(
            u,
            domain="cbf.example.com",
            base_url="https://www.cbf.example.com",
            kind=SourceKind.HTML,
            feed_urls=[list_url],
            parser_profile="cbf",
        )
    html = (
        (FIX.parent / "cbf" / "list_page.html")
        .read_bytes()
        .replace(b"www.cbf.com.br", b"www.cbf.example.com")
    )
    fake.routes[list_url] = ok(list_url, html, "text/html")
    summary = await run(db, fake, clock, source.id)
    assert summary.items_new == 3
    # Страница-список без ссылок → вероятная смена вёрстки → run error extract_empty
    fake.routes[list_url] = ok(list_url, b"<html><body>novo layout</body></html>", "text/html")
    again = await run(db, fake, clock, source.id)
    assert again.error_codes == ["extract_empty"]
