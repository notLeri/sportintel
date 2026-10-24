"""Подключение к PostgreSQL и Unit of Work (CONV §7.3)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sportintel.platform import jobs

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
STATEMENT_TIMEOUT_MS = 15_000
PING_TIMEOUT_S = 2.0

_log = structlog.get_logger("sportintel.db")

OnCommit = Callable[[], Awaitable[None]]


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._on_commit: list[OnCommit] = []

    def on_commit(self, callback: OnCommit) -> None:
        self._on_commit.append(callback)

    def enqueue_after_commit(
        self,
        task_name: str,
        *,
        queueing_lock: str | None = None,
        lock: str | None = None,
        schedule_in_seconds: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Поставить задачу после COMMIT. Потеря при падении процесса закрывается сверкой."""
        jobs.validate_task_name(task_name)
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        if request_id:
            kwargs["_request_id"] = request_id

        async def _enqueue() -> None:
            await jobs.enqueue(
                task_name,
                queueing_lock=queueing_lock,
                lock=lock,
                schedule_in_seconds=schedule_in_seconds,
                **kwargs,
            )

        _enqueue.__name__ = f"enqueue:{task_name}"
        self.on_commit(_enqueue)

    async def advisory_xact_lock(self, key: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def commit(self) -> None:
        await self.session.commit()
        callbacks, self._on_commit = self._on_commit, []
        for cb in callbacks:
            try:
                await cb()
            except Exception:
                _log.exception("platform.on_commit_failed", callback=getattr(cb, "__name__", "?"))

    async def rollback(self) -> None:
        self._on_commit = []
        await self.session.rollback()


class Database:
    def __init__(self, url: str, pool_size: int) -> None:
        self.engine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}"},
        )
        # Публичный атрибут: интеграционные тесты подменяют его сессиями в SAVEPOINT.
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        _log.info(
            "platform.db_configured", url=self.engine.url.render_as_string(hide_password=True)
        )

    @asynccontextmanager
    async def uow(self) -> AsyncIterator[UnitOfWork]:
        async with self.session_factory() as session:
            uow = UnitOfWork(session)
            try:
                yield uow
            except BaseException:
                await uow.rollback()
                raise
            await uow.commit()

    async def ping(self) -> bool:
        async def _select_one() -> None:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        try:
            await asyncio.wait_for(_select_one(), PING_TIMEOUT_S)
        except Exception:
            _log.warning("platform.db_ping_failed", exc_info=True)
            return False
        return True

    async def current_revision(self) -> str | None:
        async with self.engine.connect() as conn:
            try:
                return (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar()
            except ProgrammingError:  # таблицы нет — миграции не применялись
                return None

    async def dispose(self) -> None:
        await self.engine.dispose()


def head_revision() -> str | None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(cfg).get_current_head()


def get_database(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


async def uow_dependency(request: Request) -> AsyncIterator[UnitOfWork]:
    async with get_database(request).uow() as uow:
        yield uow


def alembic_config() -> Config:
    return Config(str(MIGRATIONS_DIR.parent / "alembic.ini"))


def migrate_cli() -> None:
    """`sportintel-migrate`: alembic upgrade head ролью migrator (Cloud Run Job, INFRA-T0.10)."""
    from alembic import command

    from sportintel.platform.config import load_settings_or_exit
    from sportintel.platform.logging import configure_logging
    from sportintel.platform.telemetry import init_telemetry

    settings = load_settings_or_exit()
    configure_logging(settings, service="migrate")
    init_telemetry(settings, "migrate")
    command.upgrade(alembic_config(), "head")
