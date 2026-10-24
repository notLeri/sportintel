import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from tests.factories import make_source

from sportintel.modules.sources import public as sources_public
from sportintel.modules.sources.domain.errors import SourceDomainExists
from sportintel.modules.sources.domain.values import SourceKind, SourceTier
from sportintel.modules.sources.infrastructure.repository import SqlSourceRepository
from sportintel.platform.db import Database
from sportintel.platform.errors import ConcurrencyConflict

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


async def test_seed_sources_present(db: Database) -> None:
    async with db.uow() as u:
        ge = await SqlSourceRepository(u.session).get_by_domain("ge.globo.com")
    assert ge is not None
    assert (ge.tier, ge.owner_group, ge.kind) == (SourceTier.A, "globo", SourceKind.RSS)


async def test_crud_and_version(db: Database) -> None:
    async with db.uow() as u:
        repo = SqlSourceRepository(u.session)
        s = await make_source(u, domain="lance.com.br")
        loaded = await repo.get(s.id)
        assert loaded is not None
        assert loaded.version == 1
        updated = await repo.update(replace(loaded, name="Lance!"), expected_version=1, now=NOW)
        assert (updated.name, updated.version) == ("Lance!", 2)
        with pytest.raises(ConcurrencyConflict):
            await repo.update(replace(loaded, name="stale"), expected_version=1, now=NOW)


async def test_duplicate_domain(db: Database) -> None:
    async with db.uow() as u:
        await make_source(u, domain="dup.example.com")
        with pytest.raises(SourceDomainExists):
            await make_source(u, domain="dup.example.com")


async def test_facade_meta_and_manual_source(db: Database) -> None:
    async with db.uow() as u:
        s = await make_source(u, domain="meta.example.com", url_keep_params=["id"])
        meta = await sources_public.get_source_meta(u, s.id)
        assert (meta.domain, meta.url_keep_params, meta.kind) == (
            "meta.example.com",
            ("id",),
            "rss",
        )
        assert (await sources_public.find_by_domain(u, "https://www.meta.example.com/x")).id == s.id  # type: ignore[union-attr]
        manual = await sources_public.ensure_manual_source(u, "https://www.blog.example.org/post/1")
        again = await sources_public.ensure_manual_source(u, "blog.example.org")
        assert (manual.kind, manual.tier, manual.id) == ("manual", None, again.id)
        many = await sources_public.get_sources_meta(u, [s.id, manual.id])
        assert set(many) == {s.id, manual.id}


@pytest.mark.integration_commit
async def test_claim_due_skip_locked_across_transactions(pg_container: str) -> None:
    db = Database(pg_container, pool_size=4)
    try:
        async with db.uow() as u:
            await u.session.execute(
                text("UPDATE sources.sources SET active = false")
            )  # seed не мешает
            for i in range(4):
                await make_source(
                    u, domain=f"due{i}.example.com", next_poll_at=NOW - timedelta(minutes=1)
                )
            await make_source(
                u,
                domain="manual-due.example.com",
                kind=SourceKind.MANUAL,
                feed_urls=[],
                next_poll_at=NOW - timedelta(hours=1),
            )
            await make_source(u, domain="future.example.com", next_poll_at=NOW + timedelta(hours=1))

        first_claimed: list = []
        claimed, release = asyncio.Event(), asyncio.Event()

        async def first() -> None:
            async with db.uow() as u:
                first_claimed.extend(await SqlSourceRepository(u.session).claim_due(NOW, limit=2))
                claimed.set()
                await release.wait()  # держим блокировки, пока работает вторая транзакция

        task = asyncio.create_task(first())
        await asyncio.wait_for(claimed.wait(), 5)
        async with db.uow() as u:
            second = await SqlSourceRepository(u.session).claim_due(NOW, limit=10)
        release.set()
        await task

        assert len(first_claimed) == 2
        assert len(second) == 2
        assert not set(first_claimed) & set(second)
        async with db.uow() as u:  # после claim next_poll_at сдвинут вперёд
            assert await SqlSourceRepository(u.session).claim_due(NOW, limit=10) == []
    finally:
        async with db.uow() as u:
            await u.session.execute(
                text("DELETE FROM sources.sources WHERE domain LIKE '%.example.com'")
            )
            await u.session.execute(text("UPDATE sources.sources SET active = true"))
        await db.dispose()
