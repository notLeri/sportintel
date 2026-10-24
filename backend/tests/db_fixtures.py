"""DB-фикстуры для integration и api тестов (CONV §13)."""

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from sportintel.platform import jobs
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database, UnitOfWork

BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_IMAGE = "pgvector/pgvector:pg16"


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def pg_container() -> Iterator[str]:
    """URL тестовой БД с применёнными миграциями. В CI — service container (TEST_DATABASE_URL)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        command.upgrade(alembic_config(url), "head")
        yield url
        return

    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(PG_IMAGE, driver="psycopg") as pg:
        url = pg.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture
def alembic_cfg(pg_container: str) -> Config:
    return alembic_config(pg_container)


@pytest.fixture
async def db(pg_container: str) -> AsyncIterator[Database]:
    """Database, все UoW которой работают в SAVEPOINT внешней транзакции с откатом."""
    database = Database(pg_container, pool_size=2)
    async with database.engine.connect() as conn:
        outer = await conn.begin()
        database.session_factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        yield database
        await outer.rollback()
    await database.dispose()


@pytest.fixture
async def uow(db: Database) -> AsyncIterator[UnitOfWork]:
    async with db.uow() as u:
        yield u


@pytest.fixture
async def committing_db(pg_container: str) -> AsyncIterator[Database]:
    """Database с реальными коммитами (маркер integration_commit) и открытым JOBS."""
    database = Database(pg_container, pool_size=2)
    jobs.set_runtime(database, FrozenClock(datetime(2026, 10, 7, 12, tzinfo=UTC)))
    await jobs.open(pg_container)
    try:
        yield database
    finally:
        await jobs.close()
        async with database.uow() as u:
            await u.session.execute(text("DELETE FROM procrastinate.procrastinate_jobs"))
        await database.dispose()
