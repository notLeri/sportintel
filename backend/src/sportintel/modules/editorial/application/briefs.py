"""AI-брифы событий: генерация на языке, хранение, заголовок для списка (фаза 3)."""

import hashlib
import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import structlog

from sportintel.modules.editorial.application.brief import (
    PROMPT_VERSION,
    EventBrief,
    brief_prompt,
    ground,
)
from sportintel.modules.events import public as events
from sportintel.platform import ai_usage, jobs, settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.config import Settings
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.llm import LlmError, LlmProvider, make_provider

_log = structlog.get_logger("sportintel.editorial")
RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
BRIEF_LANGS = {"ru", "en", "pt-BR"}
RepoFor = Callable[[UnitOfWork], Any]  # SqlBriefRepository (wiring в jobs/api)


def article_hash(article_ids: list[uuid.UUID]) -> str:
    """Тот же ключ, что считает events.brief_candidates: sha256 отсортированных id через запятую."""
    joined = ",".join(sorted(str(a) for a in article_ids))
    return hashlib.sha256(joined.encode()).hexdigest()


async def provider_for(db: Database, settings: Settings) -> LlmProvider | None:
    routing: Any = await settings_store.get(db, "ai_routing")
    return make_provider(settings, routing.llm_model)


async def build(
    db: Database,
    repo_for: RepoFor,
    event_id: uuid.UUID,
    lang: str,
    clock: Clock,
    llm: LlmProvider,
) -> dict[str, Any] | None:
    """Сгенерировать и сохранить бриф. None — у события нет статей или модель не дала опоры."""
    async with db.uow() as uow:
        pack = await events.build_evidence_pack(uow, event_id, 12, clock)
        ids = await events.event_article_ids(uow, event_id)
    if not pack.sources:
        return None
    system, user, sources = brief_prompt(pack, lang)
    t0 = time.monotonic()
    try:
        async with ai_usage.track(db, "brief", llm.model, event_id):
            raw = await llm.complete_json(system, user, EventBrief)
    except LlmError:
        _log.warning("editorial.brief_invalid", event_id=str(event_id), lang=lang, model=llm.model)
        return None
    ms = round((time.monotonic() - t0) * 1000)
    brief = ground(raw, sources)
    if brief is None:
        _log.warning("editorial.brief_ungrounded", event_id=str(event_id), lang=lang)
        return None
    row = {
        "event_id": event_id,
        "lang": lang,
        "brief": brief.model_dump(),
        "sources": [vars(s) for s in sources],
        "article_hash": article_hash(ids),
        "provider": llm.name,
        "model": llm.model,
        "prompt_version": PROMPT_VERSION,
        "duration_ms": ms,
    }
    async with db.uow() as uow:
        await repo_for(uow).upsert(row, clock.now())
        await events.set_title_translation(uow, event_id, lang, brief.headline)
    _log.info("editorial.brief_built", event_id=str(event_id), lang=lang, ms=ms, model=llm.model)
    return row


async def enqueue_due(db: Database, repo_for: RepoFor, clock: Clock) -> int:
    """Поставить брифы важным свежим событиям, у которых брифа нет или изменился состав статей."""
    cfg: Any = await settings_store.get(db, "briefs")
    async with db.uow() as uow:
        cands = await events.brief_candidates(
            uow,
            min_rank=RANK[cfg.auto_min_relevance],
            since=clock.now() - timedelta(hours=cfg.max_age_hours),
        )
        have = await repo_for(uow).hashes(
            [(e, lang) for e, _ in cands for lang in cfg.auto_languages]
        )
    n = 0
    for event_id, h in cands:
        for lang in cfg.auto_languages:
            if have.get((event_id, lang)) != h:
                n += await enqueue(event_id, lang)
    return n


async def enqueue(event_id: uuid.UUID, lang: str) -> int:
    ok = await jobs.enqueue(
        "editorial.build_brief",
        queueing_lock=f"brief:{event_id}:{lang}",
        event_id=str(event_id),
        lang=lang,
    )
    return int(ok)
