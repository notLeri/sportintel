"""Публичный фасад модуля. Другие модули импортируют только отсюда."""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sportintel.modules.events.api.router import event_filters, fresh_translations, router, to_items
from sportintel.modules.events.api.schemas import EventListItem
from sportintel.modules.events.application import evidence as _evidence
from sportintel.modules.events.application import transition_event as _tr
from sportintel.modules.events.application.evidence import EvidencePack
from sportintel.modules.events.domain.evidence import EvidenceFragment
from sportintel.modules.events.domain.values import EventStatus
from sportintel.modules.events.infrastructure import read_queries
from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.sources import public as sources
from sportintel.platform.clock import Clock, SystemClock
from sportintel.platform.db import UnitOfWork

__all__ = [
    "AutodraftCandidate",
    "EventListItem",
    "EvidenceFragment",
    "EvidencePack",
    "allowed_transitions_for",
    "approve",
    "articles_to_translate",
    "autodraft_candidates",
    "brief_candidates",
    "build_evidence_pack",
    "event_article_ids",
    "event_filters",
    "event_ids_for_articles",
    "event_status",
    "feed_events",
    "feed_events_by_ids",
    "publish_candidates",
    "router",
    "set_article_translation",
    "set_draft_status",
    "set_title_translation",
    "set_translation",
    "system_transition",
    "take_for_editing",
    "translation_candidates",
]


async def event_ids_for_articles(
    uow: UnitOfWork, ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    return await SqlEventRepository(uow.session).event_ids_for_articles(ids)


async def build_evidence_pack(
    uow: UnitOfWork, event_id: uuid.UUID, max_fragments: int = 12, clock: Clock | None = None
) -> EvidencePack:
    return await _evidence.build_evidence_pack(
        uow,
        event_id,
        max_fragments,
        clock or SystemClock(),
        lambda u: SqlEventRepository(u.session),
    )


def _repo(u: UnitOfWork) -> SqlEventRepository:
    return SqlEventRepository(u.session)


async def system_transition(uow: UnitOfWork, event_id: uuid.UUID, to: str, clock: Clock) -> bool:
    return await _tr.system_transition(uow, _repo, event_id, EventStatus(to), clock)


async def set_draft_status(
    uow: UnitOfWork, event_id: uuid.UUID, draft_state: str, last_human_author_id: uuid.UUID | None
) -> None:
    await _tr.set_draft_status(uow, _repo, event_id, draft_state, last_human_author_id)


def allowed_transitions_for(role: str) -> dict[str, list[dict[str, str]]]:
    return _tr.allowed_transitions_for(role)


@dataclass(frozen=True)
class AutodraftCandidate:
    event_id: uuid.UUID
    status: str
    basis_hash: str
    has_articles: bool


async def autodraft_candidates(
    uow: UnitOfWork, *, min_rank: int, since: datetime, limit: int = 200
) -> list[AutodraftCandidate]:
    rows = await read_queries.autodraft_candidates(uow.session, min_rank, since, limit)
    return [
        AutodraftCandidate(r["id"], r["status"], r["basis_hash"], bool(r["has_articles"]))
        for r in rows
    ]


async def brief_candidates(
    uow: UnitOfWork, *, min_rank: int, since: datetime, limit: int = 100
) -> list[tuple[uuid.UUID, str]]:
    """→ [(event_id, article_hash)] — события, которым нужен бриф."""
    rows = await read_queries.brief_candidates(uow.session, min_rank, since, limit)
    return [(r["id"], r["article_hash"]) for r in rows]


async def publish_candidates(
    uow: UnitOfWork,
    *,
    statuses: list[str],
    min_rank: int,
    since: datetime,
    limit: int = 200,
    include: list[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    """+ source_tiers {source_id: tier} — для фильтра канала «минимальный уровень источника».
    include — события, которые берутся и старше since (закреплённые на время)."""
    rows = await read_queries.publish_candidates(
        uow.session, statuses, min_rank, since, limit, include
    )
    metas = await sources.get_sources_meta(uow, {s for r in rows for s in r["source_ids"]})
    return [
        {**r, "source_tiers": {s: metas[s].tier for s in r["source_ids"] if s in metas}}
        for r in rows
    ]


async def event_article_ids(
    uow: UnitOfWork, event_id: uuid.UUID, unique_only: bool = False
) -> list[uuid.UUID]:
    """unique_only — без перепечаток (is_duplicate)."""
    return await read_queries.article_ids(uow.session, event_id, unique_only)


async def articles_to_translate(
    uow: UnitOfWork, event_id: uuid.UUID, lang: str
) -> list[dict[str, Any]]:
    """Статьи события (без перепечаток) без перевода на lang.
    same_lang — источник уже пишет на lang: перевод не нужен, сохраняется оригинал."""
    ids = await read_queries.article_ids(uow.session, event_id, unique_only=True)
    done = await ingestion.article_translations(uow, ids, lang)
    metas = await ingestion.get_articles_meta(uow, [i for i in ids if i not in done])
    srcs = await sources.get_sources_meta(uow, {m.source_id for m in metas.values()})
    return [
        {
            "id": m.id,
            "title": m.title,
            "lead": m.lead,
            "same_lang": m.source_id in srcs and srcs[m.source_id].language.startswith(lang),
        }
        for m in metas.values()
    ]


async def set_article_translation(
    uow: UnitOfWork, article_id: uuid.UUID, lang: str, title: str, lead: str | None
) -> None:
    await ingestion.set_article_translation(uow, article_id, lang, title, lead)


async def set_title_translation(
    uow: UnitOfWork, event_id: uuid.UUID, lang: str, title: str
) -> None:
    """Заголовок события на языке UI (из брифа) — для списка; оригинал не меняется."""
    await read_queries.set_title_translation(uow.session, event_id, lang, title)


async def translation_candidates(
    uow: UnitOfWork,
    lang: str,
    since: datetime,
    limit: int,
    event_id: uuid.UUID | None = None,
    min_rank: int = 2,
) -> list[dict[str, Any]]:
    return await read_queries.translation_candidates(
        uow.session, lang, since, limit, event_id, min_rank
    )


async def set_translation(
    uow: UnitOfWork, event_id: uuid.UUID, lang: str, title: str, summary: tuple[str, str] | None
) -> None:
    """Перевод заголовка и сводки на язык интерфейса; оригинал не меняется."""
    await read_queries.set_translation(uow.session, event_id, lang, title, summary)


async def event_status(uow: UnitOfWork, event_id: uuid.UUID) -> str | None:
    e = await _repo(uow).get(event_id)
    return e.status.value if e else None


async def feed_events(
    uow: UnitOfWork,
    tab: str,
    filters: read_queries.EventFilters,
    min_rank: int,
    after: tuple[Any, ...] | None,
    limit: int,
    since: datetime | None = None,
    lang: str = "ru",
    only_ids: list[uuid.UUID] | None = None,
) -> list[tuple[EventListItem, dict[str, Any]]]:
    """Строки ленты (BE-T3.15): (EventListItem, ключи курсора + сводка на языке lang).
    filters — те же, что у списка событий (event_filters)."""
    rows = await read_queries.feed_page(
        uow.session, tab, filters, min_rank, after, limit, since, only_ids
    )
    items = await to_items(uow, rows)
    return [
        (
            i,
            {
                "relevance_rank": r["relevance_rank"],
                "last_article_at": r["last_article_at"],
                "status_changed_at": r["status_changed_at"],
                "id": r["id"],
                "summary": fresh_translations(r["summary"], r["summary_i18n"]).get(lang)
                or r["summary"]
                if r["summary"]
                else None,
            },
        )
        for i, r in zip(items, rows, strict=True)
    ]


async def approve(
    uow: UnitOfWork,
    event_id: uuid.UUID,
    expected_version: int,
    actor_id: uuid.UUID,
    role: str,
    clock: Clock,
) -> None:
    """DRAFT → READY от имени пользователя («Готово»): права и проверки — как у перехода."""
    await _tr.transition_event(
        uow, _repo, event_id, EventStatus.READY, actor_id, role, expected_version, None, None,
        clock,
    )  # fmt: skip


async def take_for_editing(
    uow: UnitOfWork,
    event_id: uuid.UUID,
    expected_version: int,
    actor_id: uuid.UUID,
    role: str,
    clock: Clock,
) -> None:
    """«Взять в работу» из ленты: NEW|REVIEWING → SELECTED (пользователь) и сразу системный SELECTED → DRAFT."""
    status = await event_status(uow, event_id)
    if status is None:
        from sportintel.platform.errors import NotFound

        raise NotFound(f"event {event_id} not found")
    if status not in {"NEW", "REVIEWING"}:
        from sportintel.modules.events.domain.errors import InvalidTransition

        raise InvalidTransition(f"event is {status}")
    await _tr.transition_event(
        uow,
        _repo,
        event_id,
        EventStatus.SELECTED,
        actor_id,
        role,
        expected_version,
        None,
        None,
        clock,
    )
    await _tr.system_transition(uow, _repo, event_id, EventStatus.DRAFT, clock)


async def feed_events_by_ids(uow: UnitOfWork, ids: list[uuid.UUID]) -> list[EventListItem]:
    rows = [r for i in ids if (r := await read_queries.detail(uow.session, i)) is not None]
    return await to_items(uow, rows)
