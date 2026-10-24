"""Слияние событий и перенос статьи (BE-T4.3). Основной способ исправить недосклейку в лексическом режиме."""

import uuid
from collections.abc import Callable
from typing import Any

from sportintel.modules.audit import public as audit
from sportintel.modules.events.domain.actor import Actor
from sportintel.modules.events.domain.errors import MergeNotAllowed, SameEvent
from sportintel.modules.events.domain.event import Event
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AttachMethod,
    EventStatus,
    RejectionReason,
    RelationKind,
    Role,
    TextOrigin,
)
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.intelligence import public as intelligence
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import ConcurrencyConflict, NotFound
from sportintel.platform.ids import new_id

RepoFor = Callable[[UnitOfWork], Any]
LOCKED = {EventStatus.READY, EventStatus.PUBLISHED}


async def _lock(repo: Any, ids: list[uuid.UUID]) -> dict[uuid.UUID, Event]:
    """FOR UPDATE в порядке возрастания id — без взаимоблокировок при встречных операциях."""
    got: dict[uuid.UUID, Event] = {}
    for i in sorted(ids):
        e = await repo.get(i, for_update=True)
        if e is None:
            raise NotFound(f"event {i} not found")
        got[i] = e
    return got


def _refresh_later(uow: UnitOfWork, *ids: uuid.UUID) -> None:
    for i in ids:
        uow.enqueue_after_commit(
            "events.refresh_event", queueing_lock=f"refresh:{i}", event_id=str(i)
        )


async def merge_events(
    uow: UnitOfWork,
    repo_for: RepoFor,
    target_id: uuid.UUID,
    source_id: uuid.UUID,
    actor_id: uuid.UUID,
    role: str,
    expected_target_version: int,
    clock: Clock,
) -> None:
    if target_id == source_id:
        raise SameEvent()
    repo = repo_for(uow)
    events = await _lock(repo, [target_id, source_id])
    target, source = events[target_id], events[source_id]
    if target.version != expected_target_version:
        raise ConcurrencyConflict(current=None)
    if target.status in LOCKED or source.status in LOCKED:
        raise MergeNotAllowed("READY/PUBLISHED events cannot be merged")
    now, actor = clock.now(), Actor(actor_id, Role(role))
    moved = [source.detach(lk.article_id, now) for lk in list(source.links)]
    source.transition(
        EventStatus.REJECTED,
        actor,
        now,
        reason=RejectionReason.DUPLICATE,
        comment=f"Mesclado em {target_id}",
    )
    await repo.save(source, source.version)  # сначала освобождаем ссылки (PK article_id)
    for lk in moved:
        target.attach(
            ArticleLink(lk.article_id, now, lk.score, AttachMethod.MANUAL, True, lk.is_duplicate),
            now,
        )
    await repo.save(target, expected_target_version)
    await repo.replace_relations(source_id, RelationKind.POSSIBLE_DUPLICATE, [(target_id, None)])
    _refresh_later(uow, target_id, source_id)
    for ctx in (target_id, source_id):
        await audit.record(
            uow,
            actor_id=actor_id,
            action=audit.AuditAction.EVENT_MERGED,
            target_type="event",
            target_id=str(target_id),
            before={"source_event_id": str(source_id)},
            after={"articles": [str(lk.article_id) for lk in moved]},
            context_event_id=ctx,
        )


async def move_article(
    uow: UnitOfWork,
    repo_for: RepoFor,
    event_id: uuid.UUID,
    article_id: uuid.UUID,
    target_event_id: uuid.UUID | None,
    actor_id: uuid.UUID,
    expected_version: int,
    clock: Clock,
) -> uuid.UUID:
    if target_event_id == event_id:
        raise SameEvent()
    repo = repo_for(uow)
    events = await _lock(repo, [event_id] + ([target_event_id] if target_event_id else []))
    source = events[event_id]
    if source.version != expected_version:
        raise ConcurrencyConflict(current=None)
    if source.status in LOCKED or (target_event_id and events[target_event_id].status in LOCKED):
        raise MergeNotAllowed("READY/PUBLISHED events cannot change articles")
    now = clock.now()
    link = source.detach(article_id, now)
    await repo.save(source, expected_version)
    new_link = ArticleLink(article_id, now, None, AttachMethod.MANUAL, True, link.is_duplicate)
    if target_event_id is None:
        meta = (await ingestion.get_articles_meta(uow, [article_id]))[article_id]
        enr = await intelligence.get_enrichment(uow, article_id)
        title = (enr.headline_neutral if enr else "") or meta.title
        target = Event.create_auto(
            new_id(),
            new_link,
            title,
            TextOrigin.SOURCE,
            meta.published_at or meta.discovered_at,
            now,
        )
        if enr:
            target.sport_id, target.competition_id = enr.sport_id, enr.competition_id
        await repo.add(target)
        target_event_id = target.id
    else:
        target = events[target_event_id]
        target.attach(new_link, now)
        await repo.save(target, target.version)
    _refresh_later(uow, event_id, target_event_id)
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.EVENT_ARTICLE_MOVED,
        target_type="event",
        target_id=str(event_id),
        before={"event_id": str(event_id), "article_id": str(article_id)},
        after={"event_id": str(target_event_id)},
        context_event_id=event_id,
    )
    return target_event_id
