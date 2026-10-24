"""Задача events.cluster_article (BE-T2.15). Серая зона в режиме правил → новое событие + possible_duplicate (ADR-004)."""

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from sportintel.modules.events.domain.event import Event
from sportintel.modules.events.domain.policies.clustering import (
    ArticleFeatures,
    CandidateRow,
    decide,
    incremental_centroid,
    score,
)
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AttachMethod,
    RelationKind,
    TextOrigin,
)
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.intelligence import public as intelligence
from sportintel.modules.sources import public as sources
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform import settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.ids import new_id
from sportintel.platform.jobs import TransientError

_log = structlog.get_logger("sportintel.events")


@dataclass(frozen=True)
class ClusterOutcome:
    event_id: uuid.UUID
    method: AttachMethod
    score: float | None
    created: bool


def _best(
    feats: ArticleFeatures, cands: list[CandidateRow], p: object
) -> tuple[float, CandidateRow] | None:
    scored = [(score(feats, c, False, p), c) for c in cands]
    return max(scored, key=lambda sc: sc[0]) if scored else None


# Порты: SqlEventRepository и infrastructure.candidates.find_candidates (wiring в jobs.py).
RepoFor = Callable[[UnitOfWork], Any]
FindCandidates = Callable[..., Awaitable[list[CandidateRow]]]


async def cluster_article(
    db: Database,
    article_id: uuid.UUID,
    clock: Clock,
    repo_for: RepoFor,
    find_candidates: FindCandidates,
) -> ClusterOutcome | None:
    async with db.uow() as uow:
        meta = await ingestion.get_article_for_enrichment(uow, article_id, clock)
        if await repo_for(uow).event_id_for_article(article_id):
            if meta.state == "enriched":
                await ingestion.mark_state(uow, article_id, "clustered", clock)
            return None  # повтор задачи
        enr = await intelligence.get_enrichment(uow, article_id)
        region = (await sources.get_source_meta(uow, meta.source_id)).region
    if enr is None:
        raise TransientError("article not enriched yet")
    p: Any = await settings_store.get(db, "clustering")
    feats = ArticleFeatures(
        enr.embedding,
        frozenset(e["entity_id"] for e in enr.entities),
        enr.competition_id,
        enr.sport_id,
    )
    title = enr.headline_neutral or meta.title

    async def candidates(uow: UnitOfWork) -> list[CandidateRow]:
        return await find_candidates(
            uow.session,
            enr.embedding,
            set(feats.entity_ids),
            enr.sport_id,
            clock.now(),
            p.window_hours,
            p.top_k,
            title=title,
            lex_min=p.lex_min,
            region=region,
        )

    # Кандидаты и скоринг — вне блокировки (§14).
    async with db.uow() as uow:
        seen = await candidates(uow)
    best = _best(feats, seen, p)
    decision = decide(best[0] if best else None, p)

    async with db.uow() as uow:
        t0 = time.monotonic()
        await uow.advisory_xact_lock(f"cluster:{enr.sport_id or 'none'}")
        _log.info("events.cluster_lock_wait_ms", ms=round((time.monotonic() - t0) * 1000))
        repo = repo_for(uow)
        if await repo.event_id_for_article(article_id):
            return None  # гонка: уже прикрепила другая задача
        now = clock.now()
        event: Event | None = None
        method, sc, dup, locked = AttachMethod.AUTO, None, False, False
        if meta.target_event_id:
            event = await repo.get(meta.target_event_id, for_update=True)
            if event is None:
                _log.warning(
                    "events.target_event_missing",
                    article_id=str(article_id),
                    target=str(meta.target_event_id),
                )
            method, locked = AttachMethod.MANUAL, True
        if event is None and meta.duplicate_of:
            origin = await repo.event_id_for_article(meta.duplicate_of)
            if origin is None:
                raise TransientError("original article not clustered yet")
            event, method, dup, locked = (
                await repo.get(origin, for_update=True),
                AttachMethod.SYNDICATION,
                True,
                False,
            )
        if event is None and decision == "attach" and best:
            event, method, sc = (
                await repo.get(best[1].event_id, for_update=True),
                AttachMethod.AUTO,
                best[0],
            )
        if event is None:
            # Перепроверка под блокировкой: событие того же факта могло появиться после шага 2.
            known = {c.event_id for c in seen}
            late = _best(feats, [c for c in await candidates(uow) if c.event_id not in known], p)
            if late and decide(late[0], p) == "attach":
                event, method, sc = (
                    await repo.get(late[1].event_id, for_update=True),
                    AttachMethod.AUTO,
                    late[0],
                )

        created = event is None
        if event is None:
            link = ArticleLink(article_id, now, None, AttachMethod.NEW)
            origin_text = (
                TextOrigin.AI if enr.method == "llm" and enr.headline_neutral else TextOrigin.SOURCE
            )
            event = Event.create_auto(
                new_id(),
                link,
                title,
                origin_text,
                meta.published_at or meta.discovered_at or now,
                now,
            )
            event.sport_id, event.competition_id, event.centroid = (
                enr.sport_id,
                enr.competition_id,
                enr.embedding,
            )
            await repo.add(event)
            # Сущности сразу, а не только в refresh_event: иначе параллельная статья того же факта
            # не наберёт скор по сущностям при перепроверке под блокировкой.
            kinds = await taxonomy.get_entities(uow, feats.entity_ids)
            await repo.replace_entities(
                event.id, [(i, d.kind.value, 1, False) for i, d in kinds.items()]
            )
            method = AttachMethod.NEW
            if decision == "gray" and best:
                await repo.replace_relations(
                    event.id, RelationKind.POSSIBLE_DUPLICATE, [(best[1].event_id, best[0])]
                )
        else:
            if enr.embedding is not None and not dup:
                prior = [lk.article_id for lk in event.links if not lk.is_duplicate]
                n = len(await intelligence.get_embeddings(uow, prior))
                event.centroid = incremental_centroid(event.centroid, n, enr.embedding)
            event.attach(ArticleLink(article_id, now, sc, method, locked, dup), now)
            await repo.save(event, event.version)

        await ingestion.mark_state(uow, article_id, "clustered", clock)
        uow.enqueue_after_commit(
            "events.refresh_event", queueing_lock=f"refresh:{event.id}", event_id=str(event.id)
        )
    _log.info(
        "events.article_clustered",
        article_id=str(article_id),
        event_id=str(event.id),
        method=method.value,
        score=sc,
        created=created,
    )
    return ClusterOutcome(event.id, method, sc, created)
