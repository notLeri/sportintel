from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from tests.factories import make_user

from sportintel.modules.identity import public as identity
from sportintel.modules.identity.application import sessions as app_sessions
from sportintel.modules.identity.infrastructure.repository import SqlUserRepository
from sportintel.modules.identity.infrastructure.tables import sessions
from sportintel.modules.identity.jobs import purge_sessions_now
from sportintel.platform import jobs
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database

T0 = datetime(2026, 10, 7, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    app_sessions.clear_cache()
    yield
    app_sessions.clear_cache()


async def _count(db: Database) -> int:
    async with db.uow() as u:
        return (await u.session.execute(select(func.count()).select_from(sessions))).scalar_one()


async def test_create_resolve_revoke(db: Database) -> None:
    clock = FrozenClock(T0)
    async with db.uow() as u:
        user = await make_user(u, display_name="Ana")
        token, rec = await identity.create_session(u, user.id, "10.0.0.1", "pytest", clock)
    assert rec.id_hash != token.encode()  # в БД только хэш

    current = await identity.resolve_session(db, token, clock)
    assert current is not None
    assert (current.id, current.display_name, current.role) == (user.id, "Ana", "researcher")
    assert current.csrf_token == rec.csrf_token

    async with db.uow() as u:
        await identity.revoke_session(u, token)
    assert await identity.resolve_session(db, token, clock) is None


async def test_unknown_or_expired_token(db: Database) -> None:
    clock = FrozenClock(T0)
    assert await identity.resolve_session(db, "nope", clock) is None
    async with db.uow() as u:
        user = await make_user(u)
        token, _ = await identity.create_session(u, user.id, None, None, clock)
    clock.advance(timedelta(hours=12).total_seconds())
    assert await identity.resolve_session(db, token, clock) is None


async def test_deactivated_user_loses_access(db: Database) -> None:
    clock = FrozenClock(T0)
    async with db.uow() as u:
        user = await make_user(u)
        token, _ = await identity.create_session(u, user.id, None, None, clock)
        await SqlUserRepository(u.session).set_active(user.id, False)
    assert await identity.resolve_session(db, token, clock) is None


async def test_touch_extends_idle(db: Database) -> None:
    clock = FrozenClock(T0)
    async with db.uow() as u:
        user = await make_user(u)
        token, _ = await identity.create_session(u, user.id, None, None, clock)
    clock.advance(timedelta(hours=11).total_seconds())
    assert await identity.resolve_session(db, token, clock) is not None  # касание
    app_sessions.clear_cache()
    clock.advance(timedelta(hours=2).total_seconds())  # 13 ч от создания, 2 ч от касания
    assert await identity.resolve_session(db, token, clock) is not None


async def test_cache_hides_db_revoke_until_ttl(db: Database) -> None:
    """Удаление строки другим процессом видно после TTL кэша (≤ 30 с, §20)."""
    clock = FrozenClock(T0)
    async with db.uow() as u:
        user = await make_user(u)
        token, rec = await identity.create_session(u, user.id, None, None, clock)
    assert await identity.resolve_session(db, token, clock) is not None
    async with db.uow() as u:  # «другой процесс»: мимо revoke_session, без сброса кэша
        await u.session.execute(sessions.delete().where(sessions.c.id_hash == rec.id_hash))
    assert await identity.resolve_session(db, token, clock) is not None  # ещё в кэше
    app_sessions._cache[rec.id_hash] = (0.0, *app_sessions._cache[rec.id_hash][1:])  # TTL истёк
    assert await identity.resolve_session(db, token, clock) is None


async def test_revoke_all_for_user(db: Database) -> None:
    clock = FrozenClock(T0)
    async with db.uow() as u:
        user, other = await make_user(u), await make_user(u)
        for _ in range(3):
            await identity.create_session(u, user.id, None, None, clock)
        await identity.create_session(u, other.id, None, None, clock)
    async with db.uow() as u:
        assert await identity.revoke_all_for_user(u, user.id) == 3
    assert await _count(db) == 1


async def test_purge_removes_only_long_expired(db: Database) -> None:
    clock = FrozenClock(T0)
    async with db.uow() as u:
        user = await make_user(u)
        await identity.create_session(u, user.id, None, None, clock)  # idle истечёт T0+12h
        clock.advance(timedelta(days=10).total_seconds())
        await identity.create_session(u, user.id, None, None, clock)  # свежая
    jobs.set_runtime(db, clock)
    assert await purge_sessions_now() == 1
    assert await _count(db) == 1
