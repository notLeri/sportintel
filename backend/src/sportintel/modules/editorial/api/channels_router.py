"""Каналы Telegram (фаза 6): настройка, тестовая отправка, запуск вне расписания, журнал."""

import re
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from sportintel.modules.audit import public as audit
from sportintel.modules.editorial.application import publishing
from sportintel.modules.editorial.domain.channels import Channel, runs_until, valid_cron
from sportintel.modules.editorial.infrastructure.briefs_repository import SqlBriefRepository
from sportintel.modules.editorial.infrastructure.channels_repository import SqlChannelRepository
from sportintel.modules.editorial.infrastructure.repository import SqlDraftRepository
from sportintel.modules.identity import public as identity
from sportintel.platform import flags
from sportintel.platform.errors import FieldError, NotFound, ValidationFailed
from sportintel.platform.http_api import etag, parse_if_match
from sportintel.platform.ids import new_id
from sportintel.platform.notify import PublishError, TelegramPublisher, check_channel

P = identity.Permission
router = APIRouter(tags=["channels"], route_class=identity.PermissionedRoute)
_CHAT = re.compile(r"^(-?\d{5,20}|@[A-Za-z0-9_]{5,32})$")
Level = Literal["HIGH", "MEDIUM", "LOW"]
Tier = Literal["OFFICIAL", "A", "B", "C"]
TEST_TEXT = {
    "ru": "<b>SportIntel</b>: тестовое сообщение. Канал подключён.",
    "en": "<b>SportIntel</b>: test message. The channel is connected.",
    "pt-BR": "<b>SportIntel</b>: mensagem de teste. O canal está conectado.",
}


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    tg_chat_id: str = Field(max_length=40)
    language: Literal["ru", "en", "pt-BR"] = "en"
    mode: Literal["approval", "auto"] = "approval"
    cron: str = Field(default="0 * * * *", max_length=60)
    format: Literal["single", "digest"] = "single"
    max_per_run: int = Field(default=3, ge=1, le=20)
    min_relevance: Level = "HIGH"
    min_trust: Level = "MEDIUM"
    min_tier: Tier | None = None
    regions: list[str] = Field(default_factory=list, max_length=20)
    sports: list[str] = Field(default_factory=list, max_length=20)
    source_allow: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    source_deny: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    active: bool = True


class ChannelOut(ChannelIn):
    id: uuid.UUID
    last_run_at: datetime | None
    version: int


class ChannelList(BaseModel):
    items: list[ChannelOut]
    token_configured: bool  # TELEGRAM_BOT_TOKEN в env
    publish_enabled: bool  # FLAG_TELEGRAM_PUBLISH


class PublicationOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    status: str
    lang: str
    body_tg_html: str
    tg_message_id: int | None
    error: str | None
    created_at: datetime


class PublicationList(BaseModel):
    items: list[PublicationOut]


class QueuedPost(BaseModel):
    run_at: datetime  # UTC; в прошлом не бывает — наступивший слот отдаётся как «сейчас»
    event_ids: list[uuid.UUID]
    headline: str
    body_tg_html: str


class PlannedPost(BaseModel):
    """An event post ready to send: what gets dragged onto the calendar."""

    event_id: uuid.UUID
    headline: str
    run_at: datetime | None  # None — в очереди дальше, чем видно в календаре
    pinned: bool  # время закреплено вручную, cron его не трогает
    missed: bool  # закреплённое время прошло, пока автопостинг был выключен
    pinned_by: str | None = None  # кто закрепил


class ChannelSchedule(BaseModel):
    next_runs: list[datetime]
    queue: list[QueuedPost]  # сообщения по порядку отправки (лента «как в Telegram»)
    posts: list[PlannedPost]
    skipped: dict[str, int]  # причина → сколько подходящих событий пока не попадут в канал


class PinIn(BaseModel):
    publish_at: datetime


class ChannelTestResult(BaseModel):
    message_id: int


class ChannelCheck(BaseModel):
    """Connection check without publishing."""

    title: str
    username: str | None  # есть — канал публичный
    bot_username: str
    problem: Literal["not_admin", "cannot_post"] | None


class RunResult(BaseModel):
    sent: int
    failed: int
    skipped: int


def _validate(body: ChannelIn) -> None:
    errs = []
    if not _CHAT.fullmatch(body.tg_chat_id):
        errs.append(FieldError("tg_chat_id", "invalid", "use -100… id or @channel_username"))
    if not valid_cron(body.cron):
        errs.append(FieldError("cron", "invalid", "cron expression, e.g. 0 9,18 * * *"))
    if any(not re.fullmatch(r"[A-Z]{2}", r) for r in body.regions):
        errs.append(FieldError("regions", "invalid", "ISO 3166-1 alpha-2 codes"))
    if errs:
        raise ValidationFailed(details=errs)


def _publisher(request: Request) -> TelegramPublisher:
    token = request.app.state.settings.telegram_bot_token
    if token is None:
        raise ValidationFailed(
            details=[FieldError("tg_chat_id", "no_token", "TELEGRAM_BOT_TOKEN is not configured")]
        )
    return TelegramPublisher(token.get_secret_value())


async def _get(uow: object, channel_id: uuid.UUID) -> dict[str, object]:
    row = await SqlChannelRepository(uow.session).get(channel_id)  # type: ignore[attr-defined]
    if row is None:
        raise NotFound(f"channel {channel_id} not found")
    return row


@router.get("/api/v1/channels", openapi_extra=identity.route_permission(P.CHANNELS_MANAGE))
async def list_channels(
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> ChannelList:
    async with request.app.state.db.uow() as uow:
        rows = await SqlChannelRepository(uow.session).all()
    return ChannelList(
        items=[ChannelOut.model_validate(r) for r in rows],
        token_configured=request.app.state.settings.telegram_bot_token is not None,
        publish_enabled=flags.is_enabled("TELEGRAM_PUBLISH"),
    )


@router.post(
    "/api/v1/channels",
    status_code=201,
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def create_channel(
    body: ChannelIn,
    request: Request,
    response: Response,
    user: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> ChannelOut:
    _validate(body)
    state = request.app.state
    cid = new_id()
    async with state.db.uow() as uow:
        repo = SqlChannelRepository(uow.session)
        await repo.create({"id": cid, **body.model_dump()}, state.clock.now())
        row = await repo.get(cid)
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.CHANNEL_CREATED,
            target_type="channel",
            target_id=str(cid),
            after=body.model_dump(mode="json"),
        )
    out = ChannelOut.model_validate(row)
    response.headers["ETag"] = etag(out.version)
    return out


@router.put(
    "/api/v1/channels/{channel_id}",
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def update_channel(
    channel_id: uuid.UUID,
    body: ChannelIn,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> ChannelOut:
    _validate(body)
    state = request.app.state
    async with state.db.uow() as uow:
        before = await _get(uow, channel_id)
        repo = SqlChannelRepository(uow.session)
        await repo.update(channel_id, state.clock.now(), expected_version, **body.model_dump())
        row = await repo.get(channel_id)
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.CHANNEL_UPDATED,
            target_type="channel",
            target_id=str(channel_id),
            before=ChannelIn.model_validate(before).model_dump(mode="json"),
            after=body.model_dump(mode="json"),
        )
    out = ChannelOut.model_validate(row)
    response.headers["ETag"] = etag(out.version)
    return out


@router.post(
    "/api/v1/channels/{channel_id}:check",
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def check_channel_access(
    channel_id: uuid.UUID,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> ChannelCheck:
    """Can the bot see the channel and post to it? Nothing is sent to the channel."""
    async with request.app.state.db.uow() as uow:
        ch = await _get(uow, channel_id)
    token = request.app.state.settings.telegram_bot_token
    if token is None:
        raise ValidationFailed(
            details=[FieldError("tg_chat_id", "no_token", "TELEGRAM_BOT_TOKEN is not configured")]
        )
    try:
        info = await check_channel(token.get_secret_value(), str(ch["tg_chat_id"]))
    except PublishError as e:
        raise ValidationFailed(details=[FieldError("tg_chat_id", "telegram", str(e))]) from e
    return ChannelCheck(**info)


@router.post(
    "/api/v1/channels/{channel_id}:test",
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def send_test_message(
    channel_id: uuid.UUID,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> ChannelTestResult:
    """A real message to the channel (subscribers will see it). Works even without FLAG_TELEGRAM_PUBLISH."""
    async with request.app.state.db.uow() as uow:
        ch = await _get(uow, channel_id)
    try:
        mid = await _publisher(request).send(str(ch["tg_chat_id"]), TEST_TEXT[str(ch["language"])])
    except PublishError as e:
        raise ValidationFailed(details=[FieldError("tg_chat_id", "telegram", str(e))]) from e
    return ChannelTestResult(message_id=mid)


@router.post(
    "/api/v1/channels/{channel_id}:run",
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def run_channel_now(
    channel_id: uuid.UUID,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> RunResult:
    if not flags.is_enabled("TELEGRAM_PUBLISH"):
        raise ValidationFailed(
            details=[FieldError("mode", "publish_disabled", "FLAG_TELEGRAM_PUBLISH is off")]
        )
    state = request.app.state
    async with state.db.uow() as uow:
        ch = publishing.channel_of(await _get(uow, channel_id))
    r = await publishing.run_channel(
        state.db,
        ch,
        state.clock,
        _publisher(request),
        lambda u: SqlChannelRepository(u.session),
        lambda u: SqlDraftRepository(u.session),
        lambda u: SqlBriefRepository(u.session),
    )
    return RunResult(sent=r.sent, failed=r.failed, skipped=r.skipped)


@router.get(
    "/api/v1/channels/{channel_id}/publications",
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def list_publications(
    channel_id: uuid.UUID,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> PublicationList:
    async with request.app.state.db.uow() as uow:
        await _get(uow, channel_id)
        rows = await SqlChannelRepository(uow.session).publications(channel_id)
    return PublicationList(items=[PublicationOut.model_validate(r) for r in rows])


RUNS_AHEAD = 3  # очередь на столько запусков вперёд
READY_SHOWN = 30  # готовых постов в списке для перетаскивания
PIN_AHEAD = timedelta(days=30)
CALENDAR_AHEAD = timedelta(days=35)  # пять недель календаря
RUNS_CAP = 2000  # cron раз в минуту не должен раздувать ответ


async def _plan(
    state: object, ch: Channel, now: datetime, pins: dict[uuid.UUID, datetime]
) -> tuple[list[publishing.Post], list[tuple[publishing.Post, datetime]], dict[str, int]]:
    posts, pinned, skipped = await publishing.plan_posts(
        state.db,  # type: ignore[attr-defined]
        ch,
        now,
        lambda u: SqlChannelRepository(u.session),
        lambda u: SqlDraftRepository(u.session),
        lambda u: SqlBriefRepository(u.session),
        READY_SHOWN,
        pins,
    )
    return posts, pinned, dict(skipped)


@router.get(
    "/api/v1/channels/{channel_id}/schedule",
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def channel_schedule(
    channel_id: uuid.UUID,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> ChannelSchedule:
    """When the channel will run and what it will send: the same rules as publishing, without sending."""
    state = request.app.state
    now = state.clock.now()
    async with state.db.uow() as uow:
        ch = publishing.channel_of(await _get(uow, channel_id))
        repo = SqlChannelRepository(uow.session)
        pins = await repo.pins(channel_id)
        by = await repo.pinned_by(channel_id)
        names = await identity.user_names(uow, set(by.values()))
    runs = runs_until(ch, now, now + CALENDAR_AHEAD, RUNS_CAP)
    posts, pinned, skipped = await _plan(state, ch, now, pins)
    timed = posts[: ch.max_per_run * RUNS_AHEAD]
    queue: list[QueuedPost] = []
    planned: list[PlannedPost] = []
    for i in range(0, len(timed), ch.max_per_run):
        # ponytail: дайджест, не влезший в лимит, переносится в следующий запуск — здесь не показан
        for body, members in publishing.batches(ch, timed[i : i + ch.max_per_run]):
            at = runs[i // ch.max_per_run]
            queue.append(
                QueuedPost(
                    run_at=at,
                    event_ids=[m.event_id for m in members],
                    headline=members[0].headline if len(members) == 1 else "",
                    body_tg_html=body,
                )
            )
            planned += [PlannedPost(event_id=m.event_id, headline=m.headline, run_at=at,
                                    pinned=False, missed=False) for m in members]  # fmt: skip
    for post, at in pinned:
        late = publishing.missed(at, now)
        who = names.get(by[post.event_id]) if post.event_id in by else None
        planned.append(PlannedPost(event_id=post.event_id, headline=post.headline, run_at=at,
                                   pinned=True, missed=late, pinned_by=who))  # fmt: skip
        if not late:
            queue.append(QueuedPost(run_at=max(at, now), event_ids=[post.event_id],
                                    headline=post.headline, body_tg_html=post.body))  # fmt: skip
    planned += [PlannedPost(event_id=p.event_id, headline=p.headline, run_at=None,
                            pinned=False, missed=False) for p in posts[len(timed) :]]  # fmt: skip
    queue.sort(key=lambda q: q.run_at)
    return ChannelSchedule(next_runs=runs, queue=queue, posts=planned, skipped=skipped)


@router.put(
    "/api/v1/channels/{channel_id}/pins/{event_id}",
    status_code=204,
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def pin_post(
    channel_id: uuid.UUID,
    event_id: uuid.UUID,
    body: PinIn,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> None:
    """Pin an event post to a time (dragging onto the calendar). Only posts ready to send."""
    state = request.app.state
    now = state.clock.now()
    if body.publish_at.tzinfo is None or not now <= body.publish_at <= now + PIN_AHEAD:
        raise ValidationFailed(
            details=[FieldError("publish_at", "out_of_range", "future time within 30 days")]
        )
    async with state.db.uow() as uow:
        ch = publishing.channel_of(await _get(uow, channel_id))
    _, pinned, _ = await _plan(state, ch, now, {event_id: body.publish_at})
    if not pinned:
        raise ValidationFailed(
            details=[FieldError("event_id", "not_ready", "the event has no post for this channel")]
        )
    async with state.db.uow() as uow:
        await SqlChannelRepository(uow.session).pin(channel_id, event_id, body.publish_at, user.id)
        await _audit_post(uow, user, audit.AuditAction.CHANNEL_POST_PINNED, channel_id, event_id,
                          {"publish_at": body.publish_at.isoformat()})  # fmt: skip


@router.delete(
    "/api/v1/channels/{channel_id}/pins/{event_id}",
    status_code=204,
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def unpin_post(
    channel_id: uuid.UUID,
    event_id: uuid.UUID,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> None:
    """Unpin: the post returns to the regular scheduled queue."""
    async with request.app.state.db.uow() as uow:
        await _get(uow, channel_id)
        await SqlChannelRepository(uow.session).unpin(channel_id, event_id)
        await _audit_post(uow, user, audit.AuditAction.CHANNEL_POST_UNPINNED, channel_id, event_id)


@router.post(
    "/api/v1/channels/{channel_id}/posts/{event_id}:send",
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def send_post_now(
    channel_id: uuid.UUID,
    event_id: uuid.UUID,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> RunResult:
    """Send one ready post right away, outside the schedule and pins (like "Run now")."""
    if not flags.is_enabled("TELEGRAM_PUBLISH"):
        raise ValidationFailed(
            details=[FieldError("mode", "publish_disabled", "FLAG_TELEGRAM_PUBLISH is off")]
        )
    state = request.app.state
    async with state.db.uow() as uow:
        ch = publishing.channel_of(await _get(uow, channel_id))
    report = publishing.RunReport()
    found = await publishing.send_pinned(
        state.db,
        ch,
        {event_id: state.clock.now()},
        state.clock,
        _publisher(request),
        lambda u: SqlChannelRepository(u.session),
        lambda u: SqlDraftRepository(u.session),
        lambda u: SqlBriefRepository(u.session),
        report,
    )
    if not found:
        raise ValidationFailed(
            details=[FieldError("event_id", "not_ready", "the event has no post for this channel")]
        )
    async with state.db.uow() as uow:
        await _audit_post(uow, user, audit.AuditAction.CHANNEL_POST_SENT_NOW, channel_id, event_id,
                          {"sent": report.sent, "failed": report.failed})  # fmt: skip
    return RunResult(sent=report.sent, failed=report.failed, skipped=0)


async def _audit_post(
    uow: object,
    user: identity.CurrentUser,
    action: audit.AuditAction,
    channel_id: uuid.UUID,
    event_id: uuid.UUID,
    after: dict[str, object] | None = None,
) -> None:
    await audit.record(
        uow,  # type: ignore[arg-type]
        actor_id=user.id,
        action=action,
        target_type="channel",
        target_id=str(channel_id),
        before=None,
        after={"event_id": str(event_id), **(after or {})},
        context_event_id=event_id,
    )
