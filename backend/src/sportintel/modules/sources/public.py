"""Публичный фасад модуля sources. Другие модули импортируют только отсюда."""

import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Any

from sportintel.modules.sources.api.router import router
from sportintel.modules.sources.application import queries as _q
from sportintel.modules.sources.application.dto import SourceMeta
from sportintel.modules.sources.application.fetch_runs import FetchRunRecord, RunStatus
from sportintel.modules.sources.domain.source import normalize_domain
from sportintel.modules.sources.infrastructure.repository import (
    SqlFetchRunStore,
    SqlSourceRepository,
)
from sportintel.platform.db import UnitOfWork

__all__ = [
    "FetchRunRecord",
    "RunStatus",
    "SourceMeta",
    "ensure_manual_source",
    "find_by_domain",
    "get_feed_cache",
    "get_source_meta",
    "get_sources_meta",
    "list_health_inputs",
    "mark_fetch_result",
    "normalize_domain",
    "purge_fetch_runs",
    "record_fetch_run",
    "router",
    "set_feed_cache_entry",
]


def _store(uow: UnitOfWork) -> SqlSourceRepository:
    return SqlSourceRepository(uow.session)


async def get_source_meta(uow: UnitOfWork, source_id: uuid.UUID) -> SourceMeta:
    return await _q.get_source_meta(_store(uow), source_id)


async def get_sources_meta(
    uow: UnitOfWork, ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, SourceMeta]:
    return await _q.get_sources_meta(_store(uow), ids)


async def find_by_domain(uow: UnitOfWork, domain: str) -> SourceMeta | None:
    return await _q.find_by_domain(_store(uow), domain)


async def ensure_manual_source(uow: UnitOfWork, domain: str) -> SourceMeta:
    return await _q.ensure_manual_source(_store(uow), domain)


async def record_fetch_run(uow: UnitOfWork, run: FetchRunRecord) -> None:
    await SqlFetchRunStore(uow.session).insert(run)


async def mark_fetch_result(
    uow: UnitOfWork, source_id: uuid.UUID, ok: bool, new_items: int, now: datetime
) -> None:
    await _store(uow).mark_fetch_result(source_id, ok=ok, new_items=new_items, now=now)


async def get_feed_cache(uow: UnitOfWork, source_id: uuid.UUID) -> dict[str, Any]:
    """{feed_url: {"etag": …, "last_modified": …}} для conditional GET."""
    return await _store(uow).get_feed_cache(source_id)


async def set_feed_cache_entry(
    uow: UnitOfWork,
    source_id: uuid.UUID,
    feed_url: str,
    etag: str | None,
    last_modified: str | None,
) -> None:
    await _store(uow).set_feed_cache_entry(source_id, feed_url, etag, last_modified)


async def purge_fetch_runs(uow: UnitOfWork, before: datetime) -> int:
    """Удалить запуски старше `before` пачками (вызывается ingestion.purge_fetch_runs)."""
    return await _store(uow).purge_fetch_runs(before)


async def list_health_inputs(uow: UnitOfWork, since_7d: datetime) -> list[dict[str, Any]]:
    """Входы правил тихих отказов (BE-T4.13)."""
    from sqlalchemy import text

    rows = await uow.session.execute(
        text(
            "SELECT id, name, tier, active, last_new_article_at, consecutive_failures,"
            " coalesce(last_new_article_at >= :s, false) AS had_articles_7d FROM sources.sources WHERE kind <> 'manual'"
        ),
        {"s": since_7d},
    )
    return [dict(r._mapping) for r in rows]
