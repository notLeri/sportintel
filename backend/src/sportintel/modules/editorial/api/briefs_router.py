"""AI-брифы событий (фаза 3): прочитать бриф на языке и запросить генерацию."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from sportintel.modules.editorial.application import briefs
from sportintel.modules.editorial.application.brief import BriefSource, EventBrief, render_tg
from sportintel.modules.editorial.infrastructure.briefs_repository import SqlBriefRepository
from sportintel.modules.events import public as events
from sportintel.modules.identity import public as identity
from sportintel.platform import settings_store
from sportintel.platform.errors import FieldError, NotFound, ValidationFailed

P = identity.Permission
router = APIRouter(tags=["briefs"], route_class=identity.PermissionedRoute)
BriefLang = Literal["ru", "en", "pt-BR"]


class BriefSourceOut(BaseModel):
    n: int
    name: str
    tier: str | None
    url: str


class BriefOut(BaseModel):
    event_id: uuid.UUID
    lang: str
    brief: EventBrief
    sources: list[BriefSourceOut]
    tg_html: str
    provider: str
    model: str
    created_at: datetime
    stale: bool  # после генерации у события поменялся состав статей


class BriefQueued(BaseModel):
    queued: bool


@router.get(
    "/api/v1/events/{event_id}/briefs/{lang}",
    openapi_extra=identity.route_permission(P.EVENTS_READ),
)
async def get_brief(
    event_id: uuid.UUID,
    lang: BriefLang,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.EVENTS_READ)],
) -> BriefOut:
    db = request.app.state.db
    async with db.uow() as uow:
        row = await SqlBriefRepository(uow.session).get(event_id, lang)
        if row is None:
            raise NotFound(f"no {lang} brief for event {event_id}")
        current = briefs.article_hash(await events.event_article_ids(uow, event_id))
        pack = await events.build_evidence_pack(uow, event_id, 1, request.app.state.clock)
    drafts_cfg: Any = await settings_store.get(db, "drafts")
    brief = EventBrief.model_validate(row["brief"])
    sources = [BriefSource(**s) for s in row["sources"]]
    emoji = drafts_cfg.emojis.get(pack.sport_id) if pack.sport_id else None
    return BriefOut(
        event_id=event_id,
        lang=lang,
        brief=brief,
        sources=[BriefSourceOut(**vars(s)) for s in sources],
        tg_html=render_tg(
            brief,
            sources,
            lang,
            emoji,
            pack.occurred_at.date().isoformat() if pack.occurred_at else None,
        ),
        provider=row["provider"],
        model=row["model"],
        created_at=row["created_at"],
        stale=row["article_hash"] != current,
    )


@router.post(
    "/api/v1/events/{event_id}/briefs/{lang}:generate",
    status_code=202,
    openapi_extra=identity.route_permission(P.DRAFTS_WRITE),
)
async def generate_brief(
    event_id: uuid.UUID,
    lang: BriefLang,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.DRAFTS_WRITE)],
) -> BriefQueued:
    if await briefs.provider_for(request.app.state.db, request.app.state.settings) is None:
        raise ValidationFailed(
            details=[FieldError("lang", "ai_unavailable", "AI model is not configured")]
        )
    async with request.app.state.db.uow() as uow:
        if await events.event_status(uow, event_id) is None:
            raise NotFound(f"event {event_id} not found")
    return BriefQueued(queued=bool(await briefs.enqueue(event_id, lang)))
