"""Задачи модуля intelligence (CONV §10)."""

import uuid
from datetime import timedelta

from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.intelligence.application.enrich_article import enrich_article as run_enrich
from sportintel.modules.intelligence.infrastructure.repository import SqlEnrichmentRepository
from sportintel.platform import jobs
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork

STUCK_AFTER = timedelta(minutes=10)


def _store(uow: UnitOfWork) -> SqlEnrichmentRepository:
    return SqlEnrichmentRepository(uow.session)


@jobs.task("intelligence.enrich_article", queue="ai", retry=jobs.RetryPolicy(4, 30))
async def enrich_article(article_id: str) -> None:
    rt = jobs.runtime()
    await run_enrich(rt.db, _store, uuid.UUID(article_id), rt.clock, llm_available=False)


async def requeue_extracted(uow: UnitOfWork, clock: Clock) -> int:
    ids = await ingestion.stuck_articles(uow, "extracted", clock.now() - STUCK_AFTER)
    for i in ids:
        uow.enqueue_after_commit(
            "intelligence.enrich_article", queueing_lock=f"enrich:{i}", article_id=str(i)
        )
    return len(ids)


async def requeue_enriched(uow: UnitOfWork, clock: Clock) -> int:
    ids = await ingestion.stuck_articles(uow, "enriched", clock.now() - STUCK_AFTER)
    for i in ids:
        uow.enqueue_after_commit(
            "events.cluster_article", queueing_lock=f"cluster:{i}", article_id=str(i)
        )
    return len(ids)


jobs.register_reconcile_rule("intelligence.extracted", requeue_extracted)
jobs.register_reconcile_rule("intelligence.enriched", requeue_enriched)


RELINK_DAYS, RELINK_BATCH = 30, 500


@jobs.task("intelligence.relink_entities", queue="maintenance", retry=jobs.RetryPolicy(3, 30))
async def relink_entities(mention_norm: str, entity_id: str) -> None:
    """Новый алиас/сущность → перепривязать статьи за 30 дней пачками по 500 (BE-T4.9 §22)."""
    rt = jobs.runtime()
    since, after = rt.clock.now() - timedelta(days=RELINK_DAYS), None
    while True:
        async with rt.db.uow() as uow:
            hit, after = await _store(uow).relink_batch(
                mention_norm, uuid.UUID(entity_id), since, after, RELINK_BATCH
            )
            if hit:
                uow.enqueue_after_commit(
                    "events.refresh_for_articles", article_ids=[str(i) for i in hit]
                )
        if after is None:
            break
