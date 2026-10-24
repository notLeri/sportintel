from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from tests.factories import make_article, make_source

from sportintel.modules.ingestion.infrastructure.repository import SqlArticleRepository
from sportintel.modules.ingestion.jobs import purge_content_now, purge_fetch_runs_now
from sportintel.modules.sources import public as sources_public
from sportintel.modules.sources.infrastructure.repository import SqlSourceRepository
from sportintel.platform import jobs
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database
from sportintel.platform.ids import new_id

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


async def test_expired_text_removed_fresh_kept(db: Database) -> None:
    async with db.uow() as u:
        source = await make_source(u, domain="purge.example.com")
        old, fresh = await make_article(u, source), await make_article(u, source)
        repo = SqlArticleRepository(u.session)
        await repo.save_content(old.id, "texto antigo", NOW - timedelta(days=10), timedelta(days=7))
        await repo.save_content(fresh.id, "texto novo", NOW - timedelta(days=1), timedelta(days=7))
    jobs.set_runtime(db, FrozenClock(NOW))
    assert await purge_content_now() == 1
    async with db.uow() as u:
        left = (
            (await u.session.execute(text("SELECT article_id FROM ingestion.article_content")))
            .scalars()
            .all()
        )
    assert left == [fresh.id]


async def test_old_fetch_runs_purged(db: Database) -> None:
    async with db.uow() as u:
        source = await make_source(u, domain="runs-purge.example.com")
        for days in (40, 31, 5):
            await sources_public.record_fetch_run(
                u,
                sources_public.FetchRunRecord(
                    id=new_id(),
                    source_id=source.id,
                    feed_url=None,
                    started_at=NOW - timedelta(days=days),
                    finished_at=None,
                    status="ok",
                ),
            )
    jobs.set_runtime(db, FrozenClock(NOW))
    assert await purge_fetch_runs_now() == 2


async def _fail_runs(db: Database, source_id, n: int, now: datetime) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        for i in range(n):
            await sources_public.record_fetch_run(
                u,
                sources_public.FetchRunRecord(
                    id=new_id(),
                    source_id=source_id,
                    feed_url=None,
                    started_at=now + timedelta(seconds=i),
                    finished_at=None,
                    status="error",
                    error_code="fetch_timeout",
                ),
            )
            await sources_public.mark_fetch_result(
                u, source_id, False, 0, now + timedelta(seconds=i)
            )


async def test_five_failures_down_and_backoff_then_recovery(db: Database) -> None:
    async with db.uow() as u:
        source = await make_source(u, domain="flaky.example.com", poll_interval_seconds=300)
    await _fail_runs(db, source.id, 5, NOW)
    async with db.uow() as u:
        s = await SqlSourceRepository(u.session).get(source.id)
    assert s is not None
    assert (s.health.value, s.consecutive_failures) == ("down", 5)
    assert s.next_poll_at is not None
    assert s.next_poll_at - (NOW + timedelta(seconds=4)) == timedelta(seconds=9600)  # 300·2^5

    later = NOW + timedelta(hours=3)
    async with db.uow() as u:
        await sources_public.record_fetch_run(
            u,
            sources_public.FetchRunRecord(
                id=new_id(),
                source_id=source.id,
                feed_url=None,
                started_at=later,
                finished_at=None,
                status="not_modified",
            ),
        )
        await sources_public.mark_fetch_result(u, source.id, True, 0, later)
        s = await SqlSourceRepository(u.session).get(source.id)
    assert s is not None
    assert (s.health.value, s.consecutive_failures, s.next_poll_at) == (
        "ok",
        0,
        later + timedelta(seconds=300),
    )
    assert s.last_success_at == later
