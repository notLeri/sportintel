"""Задача intelligence.enrich_article (BE-T2.8). Основной путь — правила (ADR-004)."""

import uuid
from datetime import datetime
from typing import Any, Protocol

import structlog

from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.intelligence.application.rule_enrich import enrich_with_rules
from sportintel.modules.intelligence.domain.enrich_output import EnrichOutput
from sportintel.modules.intelligence.domain.rules import ArticleInput
from sportintel.platform import settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.jobs import TransientError

_log = structlog.get_logger("sportintel.intelligence")


class EnrichmentStore(Protocol):
    async def save(
        self,
        article_id: uuid.UUID,
        out: EnrichOutput,
        prompt_version: str,
        now: datetime,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> None: ...
    async def copy_from(
        self, article_id: uuid.UUID, original_id: uuid.UUID, now: datetime
    ) -> bool: ...


async def enrich_article(
    db: Database, store_for: Any, article_id: uuid.UUID, clock: Clock, llm_available: bool
) -> str | None:
    async with db.uow() as uow:
        art = await ingestion.get_article_for_enrichment(uow, article_id, clock)
    if art.state != "extracted":
        return None  # идемпотентность
    now = clock.now()
    if art.duplicate_of is not None:
        async with db.uow() as uow:
            if not await store_for(uow).copy_from(article_id, art.duplicate_of, now):
                raise TransientError("original not enriched yet")
            await _finish(uow, article_id, clock)
        return "copied"

    routing: Any = await settings_store.get(db, "ai_routing")
    if routing.enrich_article == "llm" and not llm_available:
        _log.info("intelligence.llm_unavailable_fallback_rules", article_id=str(article_id))
    # ponytail: LLM-ветка (промпт enrich_article/v1) — фаза L; пока всегда правила.
    rules: Any = await settings_store.get(db, "enrich_rules")
    a = ArticleInput(art.url, art.title, art.lead, art.text, (), art.language, art.published_at)
    async with db.uow() as uow:
        out = await enrich_with_rules(db, uow, a)
        await store_for(uow).save(article_id, out, f"rules/v{rules.version}", now)
        await _finish(uow, article_id, clock)
    return out.relevance.level.value


async def _finish(uow: UnitOfWork, article_id: uuid.UUID, clock: Clock) -> None:
    await ingestion.mark_state(uow, article_id, "enriched", clock)
    uow.enqueue_after_commit(
        "events.cluster_article", queueing_lock=f"cluster:{article_id}", article_id=str(article_id)
    )
