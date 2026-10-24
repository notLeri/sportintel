"""Черновики Telegram (BE-T3.7)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from sportintel.modules.audit import public as audit
from sportintel.modules.editorial.api.schemas import (
    DraftChannel,
    DraftCopied,
    DraftCreate,
    DraftDetail,
    DraftRegenerate,
    DraftSave,
    DraftTranslate,
    DraftVersionDTO,
)
from sportintel.modules.editorial.application import (
    briefs,
    drafts,
    post_ai,
    publishing,
    queries,
    translate,
)
from sportintel.modules.editorial.application.brief import BriefSource, EventBrief, render_tg
from sportintel.modules.editorial.infrastructure.briefs_repository import SqlBriefRepository
from sportintel.modules.editorial.infrastructure.channels_repository import SqlChannelRepository
from sportintel.modules.editorial.infrastructure.repository import SqlDraftRepository
from sportintel.modules.editorial.infrastructure.translations_repository import SqlTranslationCache
from sportintel.modules.events import public as events
from sportintel.modules.identity import public as identity
from sportintel.platform import ai_usage, settings_store
from sportintel.platform.errors import FieldError, NotFound, ValidationFailed
from sportintel.platform.http_api import etag, parse_if_match
from sportintel.platform.idempotency import idempotent
from sportintel.platform.llm import LlmError, LlmProvider
from sportintel.platform.rate_limit import limit_ai_generate

P = identity.Permission
router = APIRouter(tags=["drafts"], route_class=identity.PermissionedRoute)


def _repo(u: Any) -> SqlDraftRepository:
    return SqlDraftRepository(u.session)


def _cache(u: Any) -> SqlTranslationCache:
    return SqlTranslationCache(u.session)


def _unavailable(field: str) -> ValidationFailed:
    return ValidationFailed(details=[FieldError(field, "unavailable", "AI model is not connected")])


async def _llm(request: Request, field: str) -> LlmProvider:
    llm = await briefs.provider_for(request.app.state.db, request.app.state.settings)
    if llm is None:
        raise _unavailable(field)
    return llm


async def _mode(request: Request, requested: str | None) -> str:
    routing: Any = await settings_store.get(request.app.state.db, "ai_routing")
    return requested or routing.telegram_draft


async def _ai_post(request: Request, event_id: uuid.UUID, mode: str) -> drafts.BriefPost | None:
    """mode=llm: пост от ИИ по формату редакции на языке канала. Модель — вне транзакции."""
    if mode != "llm":
        return None
    state = request.app.state
    llm = await _llm(request, "mode")
    cfg: Any = await settings_store.get(state.db, "drafts")
    async with state.db.uow() as uow:
        pack = await events.build_evidence_pack(uow, event_id, 1, state.clock)
    lang = await publishing.post_language(state.db, lambda u: SqlChannelRepository(u.session))
    try:
        async with ai_usage.track(state.db, "rewrite", llm.model, event_id):
            body = await post_ai.ai_post(pack, lang, cfg, llm)
    except LlmError:
        raise _unavailable("mode") from None
    if body is None:
        return None
    row = {"lang": lang, "prompt_version": post_ai.PROMPT_VERSION, "brief": {"source_refs": []}}
    return row, body


async def _brief_post(
    request: Request, uow: Any, event_id: uuid.UUID, mode: str, lang: str | None
) -> drafts.BriefPost | None:
    """Бриф на языке поста и его Telegram HTML; None — брифа нет (сервис ответит brief_missing)."""
    if mode != "brief":
        return None
    langs: Any = await settings_store.get(request.app.state.db, "languages")
    row = await SqlBriefRepository(uow.session).get(event_id, lang or langs.telegram_language)
    if row is None:
        return None
    cfg: Any = await settings_store.get(request.app.state.db, "drafts")
    pack = await events.build_evidence_pack(uow, event_id, 1, request.app.state.clock)
    emoji = cfg.emojis.get(pack.sport_id) if pack.sport_id else None
    date = pack.occurred_at.date().isoformat() if pack.occurred_at else None
    body = render_tg(
        EventBrief.model_validate(row["brief"]),
        [BriefSource(**s) for s in row["sources"]],
        row["lang"],
        emoji,
        date,
    )
    return row, body


async def _detail(request: Request, uow: Any, draft_id: uuid.UUID) -> DraftDetail:
    langs: Any = await settings_store.get(request.app.state.db, "languages")
    d = await _repo(uow).get(draft_id)
    if d is None:
        raise NotFound(f"draft {draft_id} not found")
    pack = await events.build_evidence_pack(uow, d["event_id"], 1, request.app.state.clock)
    names = {str(s.article_id): s.source_name for s in pack.sources}
    detail = await queries.draft_detail(uow, _repo, draft_id, langs.ui_language, names)
    # куда уйдёт пост после «Готово» и почему может не уйти — редактор видит это заранее
    cur = detail["current"]
    now = request.app.state.clock.now()
    channels = []
    for row in await SqlChannelRepository(uow.session).all():
        if row["mode"] != "approval":
            continue
        ch = publishing.channel_of(row)
        why = (
            await publishing.approval_blocker(uow, ch, d["event_id"], cur["lang"], now)
            if cur
            else None
        )
        channels.append(
            DraftChannel(name=ch.name, language=ch.language, active=row["active"], blocked=why)
        )
    return DraftDetail(**detail, channels=channels)


@router.post(
    "/api/v1/events/{event_id}/drafts",
    status_code=201,
    response_model=DraftDetail,
    openapi_extra=identity.route_permission(P.DRAFTS_WRITE),
)
async def create_draft(
    event_id: uuid.UUID,
    body: DraftCreate,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.DRAFTS_WRITE)],
) -> JSONResponse:
    state = request.app.state
    limit_ai_generate(user.id)
    mode = await _mode(request, body.mode)
    async with idempotent(
        state.db,
        request,
        user.id,
        {"event_id": str(event_id), "mode": mode, "lang": body.lang},
        state.clock.now(),
    ) as idem:
        if idem.cached is not None:
            return idem.cached
        ai = await _ai_post(request, event_id, mode)
        async with state.db.uow() as uow:
            brief = ai or await _brief_post(request, uow, event_id, mode, body.lang)
            draft_id, created = await drafts.request_generation(
                state.db, uow, _repo, event_id, user.id, mode, state.clock, brief
            )
            detail = await _detail(request, uow, draft_id)
        resp = idem.store(201 if created else 200, detail.model_dump(mode="json"))
        resp.headers["ETag"] = etag(detail.version)
        return resp


@router.get("/api/v1/drafts/{draft_id}", openapi_extra=identity.route_permission(P.EVENTS_READ))
async def get_draft(
    draft_id: uuid.UUID,
    request: Request,
    response: Response,
    _: Annotated[identity.CurrentUser, identity.require(P.EVENTS_READ)],
) -> DraftDetail:
    async with request.app.state.db.uow() as uow:
        detail = await _detail(request, uow, draft_id)
    response.headers["ETag"] = etag(detail.version)
    return detail


@router.get(
    "/api/v1/drafts/{draft_id}/versions/{n}", openapi_extra=identity.route_permission(P.EVENTS_READ)
)
async def get_version(
    draft_id: uuid.UUID,
    n: int,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.EVENTS_READ)],
) -> DraftVersionDTO:
    langs: Any = await settings_store.get(request.app.state.db, "languages")
    async with request.app.state.db.uow() as uow:
        v = await _repo(uow).version(draft_id, n)
    if v is None:
        raise NotFound(f"draft version {n} not found")
    return DraftVersionDTO(**queries.version_dto(v, langs.ui_language, {}))


@router.patch("/api/v1/drafts/{draft_id}", openapi_extra=identity.route_permission(P.DRAFTS_WRITE))
async def save_draft(
    draft_id: uuid.UUID,
    body: DraftSave,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.DRAFTS_WRITE)],
) -> DraftDetail:
    state = request.app.state
    langs: Any = await settings_store.get(state.db, "languages")
    async with state.db.uow() as uow:
        await drafts.save_version(
            uow,
            _repo,
            draft_id,
            body.model_dump(),
            user.id,
            user.role,
            expected_version,
            state.clock,
            langs.telegram_language,
        )
        detail = await _detail(request, uow, draft_id)
    response.headers["ETag"] = etag(detail.version)
    return detail


@router.post(
    "/api/v1/drafts/{draft_id}:regenerate", openapi_extra=identity.route_permission(P.DRAFTS_WRITE)
)
async def regenerate_draft(
    draft_id: uuid.UUID,
    body: DraftRegenerate,
    request: Request,
    response: Response,
    user: Annotated[identity.CurrentUser, identity.require(P.DRAFTS_WRITE)],
) -> DraftDetail:
    state = request.app.state
    limit_ai_generate(user.id)
    mode = await _mode(request, body.mode)
    async with state.db.uow() as uow:
        d = await _repo(uow).get(draft_id)
    if d is None:
        raise NotFound(f"draft {draft_id} not found")
    ai = await _ai_post(request, d["event_id"], mode)
    async with state.db.uow() as uow:
        brief = ai or await _brief_post(request, uow, d["event_id"], mode, body.lang)
        await drafts.regenerate(state.db, uow, _repo, draft_id, user.id, state.clock, mode, brief)
        detail = await _detail(request, uow, draft_id)
    response.headers["ETag"] = etag(detail.version)
    return detail


@router.post(
    "/api/v1/drafts/{draft_id}:copied",
    status_code=204,
    openapi_extra=identity.route_permission(P.DRAFTS_WRITE),
)
async def draft_copied(
    draft_id: uuid.UUID,
    body: DraftCopied,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.DRAFTS_WRITE)],
) -> Response:
    """Фиксация копирования поста (BE-T3.13); каждое копирование — отдельная запись."""
    async with request.app.state.db.uow() as uow:
        repo = _repo(uow)
        d = await repo.get(draft_id)
        if d is None or await repo.version(draft_id, body.version_n) is None:
            raise NotFound(f"draft {draft_id} version {body.version_n} not found")
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.DRAFT_COPIED,
            target_type="draft",
            target_id=str(draft_id),
            after={"version_n": body.version_n},
            context_event_id=d["event_id"],
        )
    return Response(status_code=204)


@router.post(
    "/api/v1/drafts/{draft_id}:translate", openapi_extra=identity.route_permission(P.DRAFTS_WRITE)
)
async def translate_draft(
    draft_id: uuid.UUID,
    body: DraftTranslate,
    request: Request,
    response: Response,
    user: Annotated[identity.CurrentUser, identity.require(P.DRAFTS_WRITE)],
) -> DraftDetail:
    """Перевод текущей версии на ru/en — новая версия; одинаковый текст переводится один раз (кеш)."""
    state = request.app.state
    async with state.db.uow() as uow:
        d = await _repo(uow).get(draft_id)
        cur = await _repo(uow).version(draft_id, d["current_version"]) if d else None
    if d is None or cur is None:
        raise NotFound(f"draft {draft_id} not found")
    if cur["lang"] != body.lang:
        llm = await translate.translator_for(state.db, state.settings)
        if llm is None:
            raise _unavailable("lang")
        try:
            async with ai_usage.track(state.db, "translate_post", llm.model, d["event_id"]):
                text = await translate.translate(
                    state.db, _cache, llm, cur["body_tg_html"], body.lang, html=True
                )
        except LlmError:
            raise _unavailable("lang") from None
        async with state.db.uow() as uow:
            await drafts.add_translated_version(
                uow, _repo, draft_id, cur["n"], text, body.lang, user.id, state.clock
            )
    async with state.db.uow() as uow:
        detail = await _detail(request, uow, draft_id)
    response.headers["ETag"] = etag(detail.version)
    return detail
