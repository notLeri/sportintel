"""`/api/v1/events` (BE-T2.21–T2.23)."""

import hashlib
import re
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from sportintel.modules.events.api.schemas import (
    ArticleInEvent,
    ArticleSource,
    ArticleTranslation,
    AssessmentOverride,
    DraftBrief,
    EntityKindRef,
    EntityRef,
    EventDetail,
    EventListItem,
    EventPage,
    EventPatch,
    FactorOut,
    ManualEventCreate,
    ManualEventCreated,
    MergeRequest,
    MoveRequest,
    MoveResult,
    RelatedEvent,
    SkippedUrl,
    SourceRef,
    SummaryOut,
    TransitionRequest,
)
from sportintel.modules.events.application.create_manual_event import create_manual_event
from sportintel.modules.events.application.edit_event import (
    edit_event,
    request_summary_regeneration,
)
from sportintel.modules.events.application.merge_move import merge_events, move_article
from sportintel.modules.events.application.override_assessment import override_assessment
from sportintel.modules.events.application.refresh_event import refresh_event
from sportintel.modules.events.application.transition_event import transition_event
from sportintel.modules.events.domain.values import (
    EventStatus,
    RejectionReason,
    Relevance,
    Reliability,
)
from sportintel.modules.events.infrastructure import read_queries
from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.modules.identity import public as identity
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.intelligence import public as intelligence
from sportintel.modules.sources import public as sources
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform import jobs, settings_store
from sportintel.platform.errors import FieldError, NotFound, ValidationFailed
from sportintel.platform.http_api import etag, parse_if_match
from sportintel.platform.idempotency import idempotent
from sportintel.platform.pagination import decode_cursor, encode_cursor, split_multi
from sportintel.platform.rate_limit import limit_ai_generate

P = identity.Permission
router = APIRouter(prefix="/api/v1/events", tags=["events"], route_class=identity.PermissionedRoute)
TIER_ORDER = {"OFFICIAL": 0, "A": 1, "B": 2, "C": 3}
MAX_IDS = 50


def _uuids(values: list[str], name: str) -> list[uuid.UUID]:
    if len(values) > MAX_IDS:
        raise ValidationFailed(details=[FieldError(name, "too_many", f"at most {MAX_IDS} values")])
    try:
        return [uuid.UUID(v) for v in values]
    except ValueError:
        raise ValidationFailed(details=[FieldError(name, "invalid", "invalid UUID")]) from None


def _enum(values: list[str], allowed: set[str], name: str) -> list[str]:
    bad = [v for v in values if v not in allowed]
    if bad:
        raise ValidationFailed(details=[FieldError(name, "invalid", f"unknown value {bad[0]}")])
    return values


CURSOR_TYPES: dict[str, list[type]] = {
    "rank": [str, int, datetime, uuid.UUID],
    "recent": [str, datetime, uuid.UUID],
    "q": [str, float, datetime, uuid.UUID],
}


def _after(cursor: str | None, sort: str) -> tuple[Any, ...] | None:
    if not cursor:
        return None
    try:
        values = decode_cursor(cursor, CURSOR_TYPES[sort])
    except ValidationFailed:
        values = ()
    if not values or values[0] != sort:
        raise ValidationFailed(
            details=[FieldError("cursor", "invalid", f"cursor does not match sort={sort}")]
        )
    return values[1:]


def _cursor_key(row: dict[str, Any], sort: str) -> list[Any]:
    if sort == "q":
        return [sort, row["score"], row["last_article_at"], row["id"]]
    if sort == "rank":
        return [sort, row["relevance_rank"], row["last_article_at"], row["id"]]
    return [sort, row["last_article_at"], row["id"]]


_COMPETITION = re.compile(r"competition:([^(,]+)\(")


async def _rationale(uow: Any, text: str) -> str:
    """Обоснование важности — коды; названия турниров в нём — на языке интерфейса."""
    names = set(_COMPETITION.findall(text or ""))
    shown = await taxonomy.display_by_name(uow, names, await settings_store.ui_language(uow))
    return _COMPETITION.sub(lambda m: f"competition:{shown.get(m[1], m[1])}(", text or "")


async def to_items(uow: Any, rows: list[dict[str, Any]]) -> list[EventListItem]:
    metas = await sources.get_sources_meta(uow, {s for r in rows for s in r["source_ids"]})
    comps = await taxonomy.get_entities(
        uow, {r["competition_id"] for r in rows if r["competition_id"]}
    )
    lang = await settings_store.ui_language(uow)
    out = []
    for r in rows:
        srcs = sorted(
            (metas[s] for s in r["source_ids"] if s in metas),
            key=lambda m: (TIER_ORDER.get(m.tier or "", 4), m.name),
        )
        comp = comps.get(r["competition_id"]) if r["competition_id"] else None
        out.append(
            EventListItem(
                **{k: v for k, v in r.items() if k in EventListItem.model_fields},
                competition=EntityRef(id=comp.id, name=comp.display(lang)) if comp else None,
                top_sources=[SourceRef(id=m.id, name=m.name, tier=m.tier) for m in srcs[:3]],
            )
        )
    return out


def fresh_translations(summary: str, i18n: dict[str, Any]) -> dict[str, str]:
    h = hashlib.sha256(summary.encode()).hexdigest()
    # текст уже на этом языке (русский источник при русском UI) — это не перевод
    return {lang: v["t"] for lang, v in i18n.items() if v.get("h") == h and v["t"] != summary}


def event_filters(
    sport: list[str] | None = None,
    region: list[str] | None = None,
    competition: list[str] | None = None,
    relevance: list[str] | None = None,
    reliability: list[str] | None = None,
    source: list[str] | None = None,
    source_exclude: list[str] | None = None,
    entity: list[str] | None = None,
    conflicts: bool | None = None,
) -> read_queries.EventFilters:
    """Фильтры событий из query-параметров — общие для списка событий и ленты."""
    return read_queries.EventFilters(
        sport=split_multi(sport),
        region=[r.upper() for r in split_multi(region)][:MAX_IDS],
        competition=_uuids(split_multi(competition), "competition"),
        relevance=_enum(split_multi(relevance), {v.value for v in Relevance}, "relevance"),
        reliability=_enum(split_multi(reliability), {v.value for v in Reliability}, "reliability"),
        source=_uuids(split_multi(source), "source"),
        source_exclude=_uuids(split_multi(source_exclude), "source_exclude"),
        entity=_uuids(split_multi(entity), "entity"),
        conflicts=conflicts,
    )


@router.get("", openapi_extra=identity.route_permission(P.EVENTS_READ))
async def list_events(
    request: Request,
    response: Response,
    _: Annotated[identity.CurrentUser, identity.require(P.EVENTS_READ)],
    sport: Annotated[list[str] | None, Query()] = None,
    region: Annotated[list[str] | None, Query()] = None,
    competition: Annotated[list[str] | None, Query()] = None,
    relevance: Annotated[list[str] | None, Query()] = None,
    reliability: Annotated[list[str] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    source_exclude: Annotated[list[str] | None, Query()] = None,
    status: Annotated[list[str] | None, Query()] = None,
    entity: Annotated[list[str] | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    conflicts: bool | None = None,
    q: str | None = None,
    updated_since: datetime | None = None,
    sort: Literal["rank", "recent"] = "rank",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EventPage:
    if from_ and to and from_ > to:
        raise ValidationFailed(details=[FieldError("from", "invalid", "from must be <= to")])
    f = replace(
        event_filters(
            sport,
            region,
            competition,
            relevance,
            reliability,
            source,
            source_exclude,
            entity,
            conflicts,
        ),
        status=_enum(split_multi(status), {v.value for v in EventStatus}, "status"),
        from_=from_,
        to=to,
        q=(q or "").strip()[:200] or None,
        updated_since=updated_since,
    )
    mode: read_queries.Sort = "q" if f.q else sort
    after = _after(cursor, mode)
    server_time = request.app.state.clock.now()
    async with request.app.state.db.uow() as uow:
        if f.q:
            f = replace(
                f, q_entity_ids=await taxonomy.search_entities(uow, f.q, limit=5, threshold=0.5)
            )
        rows = await read_queries.list_page(uow.session, f, mode, after, limit + 1)
        page = rows[:limit]
        items = await to_items(uow, page)
    response.headers["X-Server-Time"] = server_time.isoformat()
    nxt = encode_cursor(_cursor_key(page[-1], mode)) if len(rows) > limit else None
    return EventPage(items=items, next_cursor=nxt)


async def _draft_brief(uow: Any, event_id: uuid.UUID, request: Request | None) -> DraftBrief | None:
    # editorial зависит от events, а не наоборот: brief черновика даёт composition root (main.py).
    fn = getattr(request.app.state, "draft_briefs", None) if request else None
    got = (await fn(uow, [event_id])).get(event_id) if fn else None
    return DraftBrief(**got) if got else None


INCLUDES = {"articles", "related", "draft", "conflicts"}


@router.get("/{event_id}", openapi_extra=identity.route_permission(P.EVENTS_READ))
async def get_event(
    event_id: uuid.UUID,
    request: Request,
    response: Response,
    _: Annotated[identity.CurrentUser, identity.require(P.EVENTS_READ)],
    include: Annotated[list[str] | None, Query()] = None,
) -> EventDetail:
    inc = (
        set(_enum(split_multi(include), INCLUDES, "include"))
        if include
        else {"articles", "related"}
    )
    async with request.app.state.db.uow() as uow:
        row = await read_queries.detail(uow.session, event_id)
        if row is None:
            raise NotFound(f"event {event_id} not found")
        detail = await event_detail(uow, row, inc, request)
    if detail.translation_pending:
        await _translate_now(request, event_id)
    response.headers["ETag"] = etag(row["version"])
    return detail


TRANSLATE_PRIORITY = 10


async def _translate_now(request: Request, event_id: uuid.UUID) -> None:
    """Событие открыли, а перевода нет — перевести вне очереди (фон берёт только важные)."""
    lang = await _ui_lang(request)
    lock = f"translate:{event_id}:{lang}"
    queued = await jobs.enqueue(
        "editorial.translate_event",
        queueing_lock=lock,
        priority=TRANSLATE_PRIORITY,
        event_id=str(event_id),
        lang=lang,
    )
    if not queued:  # уже ждёт в фоновой очереди — поднять
        async with request.app.state.db.uow() as uow:
            await jobs.raise_priority(uow.session, lock, TRANSLATE_PRIORITY)


async def _ui_lang(request: Request) -> str:
    langs: Any = await settings_store.get(request.app.state.db, "languages")
    return str(langs.ui_language)


async def event_detail(
    uow: Any, row: dict[str, Any], inc: set[str], request: Request | None = None
) -> EventDetail:
    """Сборка деталей через фасады пакетно (без N+1). Используется и PATCH-ответами (BE-T3.x)."""
    ids = [lk["article_id"] for lk in row["links"]]
    metas = await ingestion.get_articles_meta(uow, ids) if "articles" in inc else {}
    enr = await intelligence.get_enrichments(uow, ids) if "articles" in inc else {}
    src_ids = set(row["source_ids"]) | {m.source_id for m in metas.values()}
    row = {**row, "source_ids": list(src_ids)}
    base = (await to_items(uow, [row]))[0]
    ents = await taxonomy.get_entities(uow, [x["entity_id"] for x in row["entity_rows"]])
    srcs = await sources.get_sources_meta(uow, src_ids) if metas else {}
    lang = await _ui_lang(request) if request else None
    tr = await ingestion.article_translations(uow, ids, lang) if lang and metas else {}
    ui = lang or await settings_store.ui_language(uow)
    by_kind: dict[str, list[Any]] = {}
    for x in row["entity_rows"]:
        d = ents.get(x["entity_id"])
        if d:
            by_kind.setdefault(str(d.kind), []).append(d)
    articles = None
    if "articles" in inc:
        links = {lk["article_id"]: lk for lk in row["links"]}
        articles = []
        for m in sorted(
            metas.values(),
            key=lambda m: (m.published_at is None, m.published_at or m.discovered_at),
        ):
            s, en, lk = srcs.get(m.source_id), enr.get(m.id), links[m.id]
            articles.append(
                ArticleInEvent(
                    id=m.id,
                    title=m.title,
                    url=m.url,
                    lead=m.lead,
                    published_at=m.published_at,
                    discovered_at=m.discovered_at,
                    source=ArticleSource(
                        id=s.id,
                        name=s.name,
                        tier=s.tier,
                        owner_group=s.owner_group,
                        health=s.health,
                        language=s.language,
                    )
                    if s
                    else None,
                    is_duplicate=lk["is_duplicate"],
                    attach_method=lk["attach_method"],
                    manual=m.manual,
                    relevance=en.relevance if en else None,
                    clickbait=bool(en and en.clickbait),
                    rumor_markers=list(en.rumor_markers) if en else [],
                    image_url=m.image_url,
                    translation=ArticleTranslation(**tr[m.id]) if m.id in tr else None,
                )
            )
    related = (
        [RelatedEvent(**r) for r in await read_queries.related(uow.session, row["id"])]
        if "related" in inc
        else None
    )
    summary = (
        SummaryOut(
            text=row["summary"],
            translations=fresh_translations(row["summary"], row["summary_i18n"]),
            origin=row["summary_origin"],
            citations=row["summary_citations"] or [],
            grounding=row["summary_grounding"],
            generated_at=row["summary_generated_at"],
        )
        if row["summary"]
        else None
    )
    return EventDetail(
        **base.model_dump(),
        summary=summary,
        relevance_rationale=await _rationale(uow, row["relevance_rationale"]),
        relevance_reason=row["relevance_reason"],
        reliability_factors=[FactorOut(**f) for f in row["reliability_factors"]],
        reliability_reason=row["reliability_reason"],
        rejection_reason=row["rejection_reason"],
        rejection_comment=row["rejection_comment"],
        manual_overrides=list(row["manual_overrides"]),
        status_changed_at=row["status_changed_at"],
        created_by=row["created_by"],
        teams=[EntityRef(id=d.id, name=d.display(ui)) for d in by_kind.get("team", [])],
        players=[EntityRef(id=d.id, name=d.display(ui)) for d in by_kind.get("player", [])],
        other_entities=[
            EntityKindRef(id=d.id, kind=str(d.kind), name=d.display(ui))
            for k, ds in by_kind.items()
            if k not in {"team", "player"}
            for d in ds
        ],
        articles=articles,
        related=related,
        draft=await _draft_brief(uow, row["id"], request) if "draft" in inc else None,
        conflicts=[] if "conflicts" in inc else None,  # BE-T4.1
        original_language=articles[0].source.language if articles and articles[0].source else None,
        translation_pending=bool(
            lang
            and request
            and request.app.state.settings.ai_provider != "none"
            and (
                lang not in base.title_i18n
                or any(a.translation is None and not a.is_duplicate for a in articles or [])
            )
        ),
    )


ALL_INCLUDES = {"articles", "related", "draft", "conflicts"}


async def detail_response(
    uow: Any, event_id: uuid.UUID, response: Response, request: Request | None = None
) -> EventDetail:
    """Ответ команд — полные детали + ETag (BE-T3.2, T3.4)."""
    row = await read_queries.detail(uow.session, event_id)
    if row is None:
        raise NotFound(f"event {event_id} not found")
    response.headers["ETag"] = etag(row["version"])
    return await event_detail(uow, row, ALL_INCLUDES, request)


def _parse_enum(value: str | None, enum: Any, name: str) -> Any:
    if value is None:
        return None
    try:
        return enum(value)
    except ValueError:
        raise ValidationFailed(
            details=[FieldError(name, "invalid", f"unknown value {value}")]
        ) from None


@router.post(
    "/{event_id}/transitions", openapi_extra=identity.route_permission(P.EVENTS_TRANSITION)
)
async def post_transition(
    event_id: uuid.UUID,
    body: TransitionRequest,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_TRANSITION)],
) -> EventDetail:
    state = request.app.state
    async with state.db.uow() as uow:
        await transition_event(
            uow,
            lambda u: SqlEventRepository(u.session),
            event_id,
            _parse_enum(body.to, EventStatus, "to"),
            user.id,
            user.role,
            expected_version,
            _parse_enum(body.reason, RejectionReason, "reason"),
            body.comment,
            state.clock,
        )
        return await detail_response(uow, event_id, response, request)


def _repo(u: Any) -> SqlEventRepository:
    return SqlEventRepository(u.session)


@router.patch("/{event_id}", openapi_extra=identity.route_permission(P.EVENTS_EDIT))
async def patch_event(
    event_id: uuid.UUID,
    body: EventPatch,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_EDIT)],
) -> EventDetail:
    patch = {k: getattr(body, k) for k in body.model_fields_set}
    if patch.get("title") is None and "title" in patch:
        raise ValidationFailed(details=[FieldError("title", "required", "title cannot be null")])
    for k in ("team_ids", "player_ids"):
        if k in patch and patch[k] is None:
            patch[k] = []
    state = request.app.state
    async with state.db.uow() as uow:
        await edit_event(
            uow, _repo, event_id, patch, user.id, user.role, expected_version, state.clock
        )
        return await detail_response(uow, event_id, response, request)


@router.post(
    "/{event_id}/summary:regenerate", openapi_extra=identity.route_permission(P.EVENTS_EDIT)
)
async def regenerate_summary(
    event_id: uuid.UUID,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_EDIT)],
) -> EventDetail:
    limit_ai_generate(user.id)
    state = request.app.state
    async with state.db.uow() as uow:
        await request_summary_regeneration(
            uow, _repo, event_id, user.id, expected_version, state.clock
        )
    # ponytail: режим llm (events.generate_summary, 202) — фаза L; в rules пересчёт синхронный.
    await refresh_event(state.db, event_id, state.clock, _repo)
    async with state.db.uow() as uow:
        return await detail_response(uow, event_id, response, request)


@router.post(
    "",
    status_code=201,
    response_model=ManualEventCreated,
    openapi_extra=identity.route_permission(P.EVENTS_EDIT),
)
async def create_event(
    body: ManualEventCreate,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_EDIT)],
) -> JSONResponse:
    state = request.app.state
    now = state.clock.now()
    payload = body.model_dump(mode="json")
    async with idempotent(state.db, request, user.id, payload, now) as idem:
        if idem.cached is not None:
            return idem.cached
        async with state.db.uow() as uow:
            event_id, skipped = await create_manual_event(
                uow, _repo, body.model_dump(), user.id, user.role, state.clock
            )
            tmp = Response()
            detail = await detail_response(uow, event_id, tmp, request)
        out = ManualEventCreated(
            **detail.model_dump(), skipped_urls=[SkippedUrl(**x) for x in skipped]
        )
        resp = idem.store(201, out.model_dump(mode="json"))
        resp.headers["ETag"] = tmp.headers["ETag"]
        return resp


@router.post("/{event_id}/merge", openapi_extra=identity.route_permission(P.EVENTS_MERGE))
async def merge(
    event_id: uuid.UUID,
    body: MergeRequest,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_MERGE)],
) -> EventDetail:
    state = request.app.state
    async with state.db.uow() as uow:
        await merge_events(
            uow,
            _repo,
            event_id,
            body.other_event_id,
            user.id,
            user.role,
            expected_version,
            state.clock,
        )
    # Счётчики и оценки — сразу, чтобы ответ был актуален (задача refresh в очереди — страховка).
    for i in (event_id, body.other_event_id):
        await refresh_event(state.db, i, state.clock, _repo)
    async with state.db.uow() as uow:
        return await detail_response(uow, event_id, response, request)


@router.post(
    "/{event_id}/articles/{article_id}/move",
    openapi_extra=identity.route_permission(P.EVENTS_MERGE),
)
async def move(
    event_id: uuid.UUID,
    article_id: uuid.UUID,
    body: MoveRequest,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_MERGE)],
) -> MoveResult:
    state = request.app.state
    async with state.db.uow() as uow:
        target = await move_article(
            uow,
            _repo,
            event_id,
            article_id,
            body.target_event_id,
            user.id,
            expected_version,
            state.clock,
        )
    for i in (event_id, target):
        await refresh_event(state.db, i, state.clock, _repo)
    async with state.db.uow() as uow:
        return MoveResult(
            source=await detail_response(uow, event_id, response, request), target_event_id=target
        )


async def _override(
    kind: Any,
    event_id: uuid.UUID,
    body: AssessmentOverride,
    request: Request,
    response: Response,
    expected_version: int,
    user: identity.CurrentUser,
) -> EventDetail:
    state = request.app.state
    async with state.db.uow() as uow:
        await override_assessment(
            uow,
            _repo,
            event_id,
            kind,
            body.level,
            body.reason,
            user.id,
            user.role,
            expected_version,
            state.clock,
        )
    if body.level is None:
        await refresh_event(state.db, event_id, state.clock, _repo)
    async with state.db.uow() as uow:
        return await detail_response(uow, event_id, response, request)


@router.put(
    "/{event_id}/relevance", openapi_extra=identity.route_permission(P.EVENTS_OVERRIDE_ASSESSMENT)
)
async def put_relevance(
    event_id: uuid.UUID,
    body: AssessmentOverride,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_OVERRIDE_ASSESSMENT)],
) -> EventDetail:
    return await _override("relevance", event_id, body, request, response, expected_version, user)


@router.put(
    "/{event_id}/reliability", openapi_extra=identity.route_permission(P.EVENTS_OVERRIDE_ASSESSMENT)
)
async def put_reliability(
    event_id: uuid.UUID,
    body: AssessmentOverride,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_OVERRIDE_ASSESSMENT)],
) -> EventDetail:
    return await _override("reliability", event_id, body, request, response, expected_version, user)
