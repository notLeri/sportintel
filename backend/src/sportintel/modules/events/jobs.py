"""Фоновые задачи модуля (регистрируются через platform.jobs)."""

import uuid
from datetime import timedelta

from sportintel.modules.events.application.cluster_article import cluster_article as run_cluster
from sportintel.modules.events.application.refresh_event import refresh_event as run_refresh
from sportintel.modules.events.infrastructure.candidates import find_candidates
from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.platform import jobs
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork


def repo_for(uow: UnitOfWork) -> SqlEventRepository:
    return SqlEventRepository(uow.session)


@jobs.task("events.cluster_article", queue="cluster", retry=jobs.RetryPolicy(5, 10))
async def cluster_article(article_id: str) -> None:
    rt = jobs.runtime()
    await run_cluster(rt.db, uuid.UUID(article_id), rt.clock, repo_for, find_candidates)


@jobs.task("events.refresh_event", queue="cluster", retry=jobs.RetryPolicy(5, 10))
async def refresh_event(event_id: str) -> None:
    rt = jobs.runtime()
    await run_refresh(rt.db, uuid.UUID(event_id), rt.clock, repo_for)


async def requeue_refresh(uow: UnitOfWork, clock: Clock) -> int:
    ids = await repo_for(uow).due_refresh(clock.now() - timedelta(minutes=5))
    for i in ids:
        uow.enqueue_after_commit(
            "events.refresh_event", queueing_lock=f"refresh:{i}", event_id=str(i)
        )
    return len(ids)


jobs.register_reconcile_rule("events.refresh", requeue_refresh)


@jobs.task("events.refresh_for_articles", queue="cluster", retry=jobs.RetryPolicy(5, 10))
async def refresh_for_articles(article_ids: list[str]) -> None:
    """События этих статей → refresh (после relink сущностей, BE-T4.9)."""
    rt = jobs.runtime()
    async with rt.db.uow() as uow:
        ids = set(
            (
                await repo_for(uow).event_ids_for_articles([uuid.UUID(a) for a in article_ids])
            ).values()
        )
        await repo_for(uow).request_refresh(ids, rt.clock.now())
        for i in ids:
            uow.enqueue_after_commit(
                "events.refresh_event", queueing_lock=f"refresh:{i}", event_id=str(i)
            )
