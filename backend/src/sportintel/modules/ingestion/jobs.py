"""Задачи модуля ingestion (CONV §10)."""

import uuid
from datetime import timedelta

from sportintel.modules.ingestion.application.extract_article import (
    extract_article as run_extract_article,
)
from sportintel.modules.ingestion.application.fetch_source import fetch_source as run_fetch_source
from sportintel.modules.ingestion.domain.values import ArticleState
from sportintel.modules.ingestion.infrastructure.extractor import ExtractedPage, extract
from sportintel.modules.ingestion.infrastructure.parsers import get_profile
from sportintel.modules.ingestion.infrastructure.repository import SqlArticleRepository
from sportintel.modules.sources import public as sources
from sportintel.platform import jobs
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork

STUCK_AFTER = timedelta(minutes=10)
FETCH_RUNS_RETENTION = timedelta(days=30)


def _articles(uow: UnitOfWork) -> SqlArticleRepository:
    return SqlArticleRepository(uow.session)


@jobs.task("ingestion.fetch_source", queue="fetch", retry=jobs.RetryPolicy(3, 60))
async def fetch_source(source_id: str) -> None:
    rt = jobs.runtime()
    await run_fetch_source(
        rt.db, _articles, uuid.UUID(source_id), rt.fetcher, rt.clock, get_profile
    )


def extract_with_profile(html: bytes, url: str, profile_name: str) -> ExtractedPage:
    """trafilatura + коррекции профиля (BE-T1.8). CPU — вызывается в потоке."""
    return get_profile(profile_name).postprocess(extract(html, url), html, url)


@jobs.task("ingestion.extract_article", queue="fetch", retry=jobs.RetryPolicy(3, 60))
async def extract_article(article_id: str) -> None:
    rt = jobs.runtime()
    await run_extract_article(
        rt.db, _articles, uuid.UUID(article_id), rt.fetcher, rt.clock, extract_with_profile
    )


async def requeue_discovered(uow: UnitOfWork, clock: Clock) -> int:
    """Сверка: статья застряла в discovered (упал процесс до постановки) → extract_article."""
    ids = await _articles(uow).stuck_in_state(ArticleState.DISCOVERED, clock.now() - STUCK_AFTER)
    for article_id in ids:
        uow.enqueue_after_commit(
            "ingestion.extract_article",
            queueing_lock=f"extract:{article_id}",
            article_id=str(article_id),
        )
    return len(ids)


jobs.register_reconcile_rule("ingestion.discovered", requeue_discovered)


async def purge_content_now() -> int:
    """Текст статей хранится ограниченно (SRS §16, copyright): просроченный удаляется."""
    rt = jobs.runtime()
    async with rt.db.uow() as uow:
        return await _articles(uow).purge_expired_content(rt.clock.now())


async def purge_fetch_runs_now() -> int:
    rt = jobs.runtime()
    async with rt.db.uow() as uow:
        return await sources.purge_fetch_runs(uow, rt.clock.now() - FETCH_RUNS_RETENTION)


@jobs.periodic("ingestion.purge_content", cron="23 * * * *")
async def purge_content(timestamp: int) -> None:
    await purge_content_now()


@jobs.periodic("ingestion.purge_fetch_runs", cron="30 4 * * *")
async def purge_fetch_runs(timestamp: int) -> None:
    await purge_fetch_runs_now()


@jobs.task("ingestion.preview_fetch", queue="fetch", retry=jobs.RetryPolicy(1, 30))
async def preview_fetch(preview_id: str) -> None:
    from sportintel.modules.ingestion.application.preview_fetch import preview_fetch as run_preview

    rt = jobs.runtime()
    await run_preview(rt.db, uuid.UUID(preview_id), rt.fetcher, get_profile, extract_with_profile)
