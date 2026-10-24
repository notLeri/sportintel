"""Публичный фасад модуля editorial."""

import uuid
from collections.abc import Collection
from typing import Any

from sportintel.modules.editorial.api.briefs_router import router as briefs_router
from sportintel.modules.editorial.api.channels_router import router as channels_router
from sportintel.modules.editorial.api.feed_router import router as feed_router
from sportintel.modules.editorial.api.router import router
from sportintel.modules.editorial.application.autodraft import post_interval_s
from sportintel.modules.editorial.infrastructure.repository import SqlDraftRepository
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork

__all__ = [
    "ai_backlog",
    "briefs_router",
    "channel_chat_id",
    "channels_router",
    "draft_briefs",
    "drafts_failed_since",
    "feed_router",
    "post_interval_s",
    "router",
]


async def channel_chat_id(uow: UnitOfWork, channel_id: uuid.UUID) -> str | None:
    """tg_chat_id канала (None — канала нет): лента канала собирается в composition."""
    from sportintel.modules.editorial.infrastructure.channels_repository import (
        SqlChannelRepository,
    )

    row = await SqlChannelRepository(uow.session).get(channel_id)
    return str(row["tg_chat_id"]) if row else None


async def draft_briefs(
    uow: UnitOfWork, event_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """DraftBrief для EventDetail.draft (склейка в composition root)."""
    rows = await SqlDraftRepository(uow.session).by_events(list(event_ids))
    return {
        k: {
            "id": r["id"],
            "state": r["state"],
            "current_version": r["current_version"],
            "updated_at": r["updated_at"],
        }
        for k, r in rows.items()
    }


async def drafts_failed_since(uow: UnitOfWork, since: Any) -> int:
    from sqlalchemy import text

    return int(
        (
            await uow.session.execute(
                text(
                    "SELECT count(*) FROM editorial.telegram_drafts WHERE state = 'failed' AND updated_at >= :s"
                ),
                {"s": since},
            )
        ).scalar()
        or 0
    )


async def ai_backlog(db: Database, clock: Clock) -> dict[str, list[uuid.UUID]]:
    """Очереди ИИ по порядку: post — событиям нужен пост от ИИ, translate — перевод на язык
    интерфейса. ponytail: перевод — не больше 2000 событий в подсчёте."""
    from sportintel.modules.editorial.application import autodraft, translate
    from sportintel.modules.editorial.infrastructure.channels_repository import (
        SqlChannelRepository,
    )

    posts = await autodraft.ai_backlog(
        db,
        lambda u: SqlDraftRepository(u.session),
        lambda u: SqlChannelRepository(u.session),
        clock,
    )
    rows = await translate.backlog(db, clock, autodraft.BACKLOG)
    return {"post": posts, "translate": [r["id"] for r in rows]}
