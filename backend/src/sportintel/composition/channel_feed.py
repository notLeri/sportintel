"""Лента канала для вкладки «Автопостинг»: что уже видят подписчики (склейка editorial и ingestion)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel

from sportintel.modules.editorial import public as editorial
from sportintel.modules.identity import public as identity
from sportintel.modules.ingestion import public as ingestion
from sportintel.platform.errors import NotFound
from sportintel.platform.notify import PublishError, channel_username, fetch_public_channel

P = identity.Permission
router = APIRouter(tags=["channels"], route_class=identity.PermissionedRoute)


class LinkPreview(BaseModel):
    url: str | None = None
    site: str | None = None
    title: str | None = None
    description: str | None = None
    image: str | None = None


class Document(BaseModel):
    title: str | None = None
    extra: str | None = None  # размер файла


class Reaction(BaseModel):
    emoji: str
    count: str  # как на t.me: «12», «1.2K»


class ChannelPost(BaseModel):
    url: str
    html: str  # Bot API HTML (b, i, a, blockquote, tg-spoiler…); UI санитизирует ещё раз
    published_at: datetime | None
    edited: bool
    views: str | None
    author: str | None
    forwarded_from: str | None
    photos: list[str]
    video_thumb: str | None
    sticker: str | None
    unsupported: bool  # медиа, которое t.me не показывает (опрос, голосовое…)
    reactions: list[Reaction]
    link_preview: LinkPreview | None
    document: Document | None


class ChannelFeed(BaseModel):
    # live — публичный канал прочитан с t.me; иначе UI показывает журнал публикаций
    live: bool
    reason: str | None  # private_chat_id | unavailable
    items: list[ChannelPost]
    username: str | None = None  # без @; ссылка t.me/<username>
    title: str | None = None
    avatar_url: str | None = None
    subscribers: str | None = None  # как на t.me: «20.8K»


@router.get(
    "/api/v1/channels/{channel_id}/feed",
    openapi_extra=identity.route_permission(P.CHANNELS_MANAGE),
)
async def channel_feed(
    channel_id: uuid.UUID,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.CHANNELS_MANAGE)],
) -> ChannelFeed:
    async with request.app.state.db.uow() as uow:
        chat_id = await editorial.channel_chat_id(uow, channel_id)
    if chat_id is None:
        raise NotFound(f"channel {channel_id} not found")
    token = request.app.state.settings.telegram_bot_token
    try:
        # числовой id публичного канала: username узнаём у Bot API
        username = (
            chat_id[1:]
            if chat_id.startswith("@")
            else token and await channel_username(token.get_secret_value(), chat_id)
        )
        if not username:
            return ChannelFeed(live=False, reason="private_chat_id", items=[])
        page = ingestion.telegram_channel_page(await fetch_public_channel(username))
    except PublishError:
        return ChannelFeed(live=False, reason="unavailable", items=[])
    return ChannelFeed(
        live=True,
        reason=None,
        items=[ChannelPost(**p) for p in page["posts"]],
        username=username,
        title=page["title"],
        avatar_url=page["avatar_url"],
        subscribers=page["subscribers"],
    )
