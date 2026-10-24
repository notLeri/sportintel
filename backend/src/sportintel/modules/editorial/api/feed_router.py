"""Лента: быстрый отбор событий прямо в автопостинг.

Карточка — событие на языке интерфейса; первый вариант поста создаётся автоматически; «Одобрить» = «Готово»,
«Запланировать» = «Готово» + закрепление в календаре канала; «Переписать» — если вариант слаб.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel

from sportintel.modules.audit import public as audit
from sportintel.modules.editorial.api import router as drafts_api
from sportintel.modules.editorial.api.channels_router import PIN_AHEAD
from sportintel.modules.editorial.api.schemas import DraftRegenerate
from sportintel.modules.editorial.application import drafts, publishing
from sportintel.modules.editorial.application.autodraft import RANK
from sportintel.modules.editorial.disclaimers import render
from sportintel.modules.editorial.infrastructure.channels_repository import SqlChannelRepository
from sportintel.modules.editorial.infrastructure.repository import SqlDraftRepository
from sportintel.modules.events import public as events
from sportintel.modules.identity import public as identity
from sportintel.platform import settings_store
from sportintel.platform.errors import FieldError, NotFound, ValidationFailed
from sportintel.platform.http_api import parse_if_match
from sportintel.platform.pagination import decode_cursor, encode_cursor
from sportintel.platform.rate_limit import limit_ai_generate

P = identity.Permission
router = APIRouter(prefix="/api/v1/feed", tags=["feed"], route_class=identity.PermissionedRoute)
CURSOR: dict[str, list[type]] = {
    "suggested": [str, int, datetime, uuid.UUID],
    "channel": [str, datetime, uuid.UUID],
}


class FeedDraft(BaseModel):
    id: uuid.UUID
    version_n: int
    origin: str
    body_tg_html: str
    disclaimer_text: str | None
    image_url: str | None
    lang: str


class FeedSource(BaseModel):
    name: str
    url: str
    tier: str | None


class FeedItem(BaseModel):
    event: events.EventListItem
    title: str  # на языке интерфейса, если перевод готов
    summary: str | None
    draft: FeedDraft | None
    sources: list[FeedSource]


class FeedChannel(BaseModel):
    id: uuid.UUID
    name: str
    language: str
    active: bool


class FeedPage(BaseModel):
    items: list[FeedItem]
    next_cursor: str | None
    channels: list[FeedChannel]  # куда можно запланировать пост


class ScheduleIn(BaseModel):
    channel_id: uuid.UUID
    publish_at: datetime


class TakeResult(BaseModel):
    event: events.EventListItem
    draft_id: uuid.UUID | None


@router.get("", openapi_extra=identity.route_permission(P.EVENTS_READ))
async def get_feed(
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.EVENTS_READ)],
    tab: Literal["suggested", "channel"] = "suggested",
    sport: Annotated[list[str] | None, Query()] = None,
    region: Annotated[list[str] | None, Query()] = None,
    competition: Annotated[list[str] | None, Query()] = None,
    relevance: Annotated[list[str] | None, Query()] = None,
    reliability: Annotated[list[str] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    source_exclude: Annotated[list[str] | None, Query()] = None,
    entity: Annotated[list[str] | None, Query()] = None,
    conflicts: bool | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FeedPage:
    state = request.app.state
    cfg: Any = await settings_store.get(state.db, "drafts")
    langs: Any = await settings_store.get(state.db, "languages")
    after = None
    if cursor:
        values = decode_cursor(cursor, CURSOR[tab])
        if values[0] != tab:
            raise ValidationFailed(
                details=[FieldError("cursor", "invalid", "cursor does not match tab")]
            )
        after = values[1:]
    filters = events.event_filters(
        sport, region, competition, relevance, reliability, source, source_exclude, entity,
        conflicts,
    )  # fmt: skip
    now = state.clock.now()
    since = now - publishing.WINDOW
    suggested = tab == "suggested"
    # «Предложения» — только посты на языке канала: пост на другом языке ждёт версию ИИ
    lang = await publishing.post_language(state.db, lambda u: SqlChannelRepository(u.session))
    async with state.db.uow() as uow:
        only = (
            await SqlDraftRepository(uow.session).events_with_post_in(lang, since)
            if suggested
            else None
        )
        rows = await events.feed_events(
            uow,
            tab,
            filters,
            RANK[cfg.auto_min_relevance],
            after,
            limit + 1,
            since=since if suggested else None,
            lang=langs.ui_language,
            only_ids=only,
        )
        page = rows[:limit]
        repo = SqlDraftRepository(uow.session)
        drafts = await repo.by_events([e.id for e, _ in page])
        items = []
        for e, key in page:
            d = drafts.get(e.id)
            v = (
                await repo.version(d["id"], d["current_version"])
                if d and d["current_version"]
                else None
            )
            # ponytail: pack на каждый пост (≤ 50) ради ссылок источников; пакетный запрос — если лента станет медленной.
            pack = await events.build_evidence_pack(uow, e.id, 1, state.clock)
            items.append(
                FeedItem(
                    event=e,
                    title=e.title_i18n.get(langs.ui_language) or e.title,
                    summary=key["summary"],
                    draft=FeedDraft(
                        id=d["id"],
                        version_n=v["n"],
                        origin=v["origin"],
                        body_tg_html=v["body_tg_html"],
                        disclaimer_text=None
                        if v["disclaimer_removed"]
                        else render(list(v["disclaimer_kinds"]), langs.ui_language),
                        image_url=v["image_url"],
                        lang=v["lang"],
                    )
                    if d and v
                    else None,
                    sources=[
                        FeedSource(name=s.source_name, url=s.url, tier=s.tier) for s in pack.sources
                    ],
                )
            )
        channels = [
            FeedChannel(id=c["id"], name=c["name"], language=c["language"], active=c["active"])
            for c in await SqlChannelRepository(uow.session).all()
        ]
    nxt = None
    if len(rows) > limit:
        k = page[-1][1]
        nxt = encode_cursor(
            [tab, k["relevance_rank"], k["last_article_at"], k["id"]]
            if tab == "suggested"
            else [tab, k["status_changed_at"], k["id"]]
        )
    return FeedPage(items=items, next_cursor=nxt, channels=channels)


@router.post("/{event_id}:take", openapi_extra=identity.route_permission(P.EVENTS_TRANSITION))
async def take(
    event_id: uuid.UUID,
    request: Request,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_TRANSITION)],
) -> TakeResult:
    state = request.app.state
    async with state.db.uow() as uow:
        await uow.advisory_xact_lock(f"draft:{event_id}")
        await events.take_for_editing(
            uow, event_id, expected_version, user.id, user.role, state.clock
        )
        d = await SqlDraftRepository(uow.session).by_event(event_id)
        rows = await events.feed_events_by_ids(uow, [event_id])
    return TakeResult(event=rows[0], draft_id=d["id"] if d else None)


@router.post(
    "/{event_id}:prepare", status_code=204, openapi_extra=identity.route_permission(P.DRAFTS_WRITE)
)
async def prepare_post(
    event_id: uuid.UUID,
    body: DraftRegenerate,
    request: Request,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.DRAFTS_WRITE)],
) -> Response:
    """Prepare post: the event is taken into work (if not already) and gets a new post,
    written by AI in the editorial format in the channel's language, or from a template.
    The model runs outside the transaction."""
    state = request.app.state
    limit_ai_generate(user.id)
    mode = await drafts_api._mode(request, body.mode)
    if mode not in {"llm", "template"}:
        raise ValidationFailed(details=[FieldError("mode", "invalid", "llm or template")])
    ai = await drafts_api._ai_post(request, event_id, mode)
    async with state.db.uow() as uow:
        await uow.advisory_xact_lock(f"draft:{event_id}")
        if await events.event_status(uow, event_id) in {"NEW", "REVIEWING"}:
            await events.take_for_editing(
                uow, event_id, expected_version, user.id, user.role, state.clock
            )
        repo = SqlDraftRepository(uow.session)
        d = await repo.by_event(event_id)
        if d is None:
            await drafts.request_generation(
                state.db,
                uow,
                drafts_api._repo,
                event_id,
                user.id,
                mode,
                state.clock,
                ai,
            )
        else:
            await drafts.regenerate(
                state.db,
                uow,
                drafts_api._repo,
                d["id"],
                user.id,
                state.clock,
                mode,
                ai,
            )
    return Response(status_code=204)


async def _approve_current(
    uow: Any,
    state: Any,
    event_id: uuid.UUID,
    expected_version: int,
    user: identity.CurrentUser,
    channels: list[dict[str, Any]],
) -> None:
    """Утвердить текущий вариант поста («Готово»), из какого бы статуса до «Готово» ни было
    событие: новое берётся в работу, взятое — переводится в черновик, затем «Готово».
    Отказ, если ни один из channels пост не возьмёт (язык, фильтры, давность)."""
    repo = SqlDraftRepository(uow.session)
    d = await repo.by_event(event_id)
    v = await repo.version(d["id"], d["current_version"]) if d and d["current_version"] else None
    if v is None or not v["body_tg_html"].strip():
        raise ValidationFailed(details=[FieldError("event_id", "no_post", "prepare a post first")])
    status = await events.event_status(uow, event_id)
    if status in {"NEW", "REVIEWING", "SELECTED"}:
        if status == "SELECTED":
            await events.system_transition(uow, event_id, "DRAFT", state.clock)
        else:
            await events.take_for_editing(
                uow, event_id, expected_version, user.id, user.role, state.clock
            )
        expected_version = (await events.feed_events_by_ids(uow, [event_id]))[0].version
        status = "DRAFT"
    if status == "DRAFT":
        await events.approve(uow, event_id, expected_version, user.id, user.role, state.clock)
    elif status != "READY":
        raise ValidationFailed(
            details=[FieldError("event_id", "not_approvable", f"event is {status}")]
        )
    now = state.clock.now()
    blockers = [
        await publishing.approval_blocker(uow, publishing.channel_of(c), event_id, v["lang"], now)
        for c in channels
    ]
    if channels and all(blockers):
        raise ValidationFailed(
            details=[FieldError("channel_id", str(blockers[0]), "post will not be sent")]
        )


@router.post(
    "/{event_id}:approve",
    status_code=204,
    openapi_extra=identity.route_permission(P.EVENTS_TRANSITION),
)
async def approve_post(
    event_id: uuid.UUID,
    request: Request,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_TRANSITION)],
) -> Response:
    """Approve: the current post version becomes "Ready" and goes to channels on their schedules.
    Also works for the first automatic version of a new event."""
    state = request.app.state
    async with state.db.uow() as uow:
        await uow.advisory_xact_lock(f"draft:{event_id}")
        channels = await SqlChannelRepository(uow.session).all()
        await _approve_current(uow, state, event_id, expected_version, user, channels)
    return Response(status_code=204)


@router.post(
    "/{event_id}:schedule",
    status_code=204,
    openapi_extra=identity.route_permission(P.EVENTS_TRANSITION),
)
async def schedule_post(
    event_id: uuid.UUID,
    body: ScheduleIn,
    request: Request,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_TRANSITION)],
) -> Response:
    """Schedule: approve the current post and pin it in a channel at a time.
    All in one transaction: if the post would not go to the channel (language, filters), nothing changes."""
    state = request.app.state
    now = state.clock.now()
    if body.publish_at.tzinfo is None or not now <= body.publish_at <= now + PIN_AHEAD:
        raise ValidationFailed(
            details=[FieldError("publish_at", "out_of_range", "future time within 30 days")]
        )
    async with state.db.uow() as uow:
        await uow.advisory_xact_lock(f"draft:{event_id}")
        row = await SqlChannelRepository(uow.session).get(body.channel_id)
        if row is None:
            raise NotFound(f"channel {body.channel_id} not found")
        await _approve_current(uow, state, event_id, expected_version, user, [row])
        await SqlChannelRepository(uow.session).pin(
            body.channel_id, event_id, body.publish_at, user.id
        )
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.CHANNEL_POST_PINNED,
            target_type="channel",
            target_id=str(body.channel_id),
            after={"event_id": str(event_id), "publish_at": body.publish_at.isoformat(),
                   "from": "feed"},
        )  # fmt: skip
    return Response(status_code=204)
