"""`/api/v1/articles` (BE-T1.10; список и поиск — BE-T1.11)."""

import uuid
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from sportintel.modules.identity import public as identity
from sportintel.modules.ingestion.api.schemas import (
    ArticleDetail,
    ArticleListItem,
    ArticlePage,
    ArticleSourceRef,
    ManualArticleAccepted,
    ManualArticleCreate,
)
from sportintel.modules.ingestion.application.ingest_manual_url import ingest_manual_url
from sportintel.modules.ingestion.domain.values import ArticleState
from sportintel.modules.ingestion.infrastructure import read_queries
from sportintel.modules.ingestion.infrastructure.repository import SqlArticleRepository
from sportintel.modules.sources import public as sources
from sportintel.platform import settings_store
from sportintel.platform.errors import FieldError, NotFound, ValidationFailed
from sportintel.platform.idempotency import idempotent
from sportintel.platform.pagination import decode_cursor, encode_cursor, split_multi

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/articles", tags=["articles"], route_class=identity.PermissionedRoute
)


@router.post(
    "",
    status_code=202,
    response_model=ManualArticleAccepted,
    openapi_extra=identity.route_permission(P.ARTICLES_CREATE),
)
async def add_manual_article(
    body: ManualArticleCreate,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.ARTICLES_CREATE)],
) -> JSONResponse:
    state = request.app.state
    now = state.clock.now()
    payload = body.model_dump(mode="json")
    async with idempotent(state.db, request, user.id, payload, now) as idem:
        if idem.cached is not None:
            return idem.cached
        async with state.db.uow() as uow:
            result = await ingest_manual_url(
                uow, SqlArticleRepository(uow.session), body.url, user.id, now, body.target_event_id
            )
        accepted = ManualArticleAccepted(
            article_id=result.article_id, created=result.created, state=result.state.value
        )
        return idem.store(202, accepted.model_dump(mode="json"))


EventIdsFor = Callable[[Collection[uuid.UUID]], Awaitable[dict[uuid.UUID, uuid.UUID]]]


EnrichmentFor = Callable[
    [Collection[uuid.UUID]], Awaitable[dict[uuid.UUID, tuple[str | None, str]]]
]


async def _enrichment(
    request: Request, ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str | None, str]]:
    fn: EnrichmentFor | None = getattr(request.app.state, "enrichment_for_articles", None)
    return await fn(ids) if fn and ids else {}


async def _event_ids(request: Request, ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    # Склейка с events — через функцию из composition root (BE-T1.11 §12); до BE-T2.15 её нет.
    fn: EventIdsFor | None = getattr(request.app.state, "event_ids_for_articles", None)
    return await fn(ids) if fn and ids else {}


def _item(
    row: dict[str, Any],
    metas: dict[uuid.UUID, Any],
    events: dict[uuid.UUID, uuid.UUID],
    enr: dict[uuid.UUID, tuple[str | None, str]] | None = None,
) -> dict[str, Any]:
    meta = metas.get(row["source_id"])
    sport, relevance = (enr or {}).get(row["id"], (None, None))
    return {
        "id": row["id"],
        "title": row["title"],
        "url": row["original_url"],
        "source": ArticleSourceRef(id=meta.id, name=meta.name, domain=meta.domain, tier=meta.tier)
        if meta
        else None,
        "published_at": row["published_at"],
        "discovered_at": row["discovered_at"],
        "state": row["state"],
        "failure_code": row["failure_code"],
        "manual": row["manual"],
        "image_url": row["image_url"],
        "event_id": events.get(row["id"]),
        "sport_id": sport,
        "relevance": relevance,
    }


def _uuids(values: list[str], field: str) -> list[uuid.UUID]:
    try:
        return [uuid.UUID(v) for v in values]
    except ValueError:
        raise ValidationFailed(details=[FieldError(field, "invalid", "expected UUID")]) from None


@router.get("", openapi_extra=identity.route_permission(P.ARTICLES_READ))
async def list_articles(
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.ARTICLES_READ)],
    source: Annotated[list[str] | None, Query()] = None,
    state: Annotated[list[str] | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ArticlePage:
    states = split_multi(state)
    bad = [s for s in states if s not in {v.value for v in ArticleState}]
    if bad:
        raise ValidationFailed(details=[FieldError("state", "invalid", f"unknown state {bad[0]}")])
    if from_ and to and from_ > to:
        raise ValidationFailed(details=[FieldError("from", "invalid", "from must be <= to")])
    text_q = (q or "").strip()[:200] or None
    f = read_queries.ArticleFilters(
        _uuids(split_multi(source), "source"), states, from_, to, text_q
    )
    types: list[type] = [float, datetime, uuid.UUID] if text_q else [datetime, uuid.UUID]
    after = decode_cursor(cursor, types) if cursor else None
    async with request.app.state.db.uow() as uow:
        rows = await read_queries.list_page(uow.session, f, after, limit + 1)
        metas = await sources.get_sources_meta(uow, {r["source_id"] for r in rows})
        lang = await settings_store.ui_language(uow)
        tr = await SqlArticleRepository(uow.session).translations([r["id"] for r in rows], lang)
    page = rows[:limit]
    nxt = None
    if len(rows) > limit:
        last = page[-1]
        nxt = encode_cursor(
            (last["rank"], last["discovered_at"], last["id"])
            if text_q
            else (last["sort_ts"], last["id"])
        )
    events = await _event_ids(request, [r["id"] for r in page])
    return ArticlePage(
        items=[
            ArticleListItem(
                **_item(r, metas, events),
                title_translated=tr[r["id"]]["title"] if r["id"] in tr else None,
            )
            for r in page
        ],
        next_cursor=nxt,
    )


@router.get("/{article_id}", openapi_extra=identity.route_permission(P.ARTICLES_READ))
async def get_article(
    article_id: uuid.UUID,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.ARTICLES_READ)],
) -> ArticleDetail:
    async with request.app.state.db.uow() as uow:
        row = await read_queries.detail(uow.session, article_id)
        if row is None:
            raise NotFound(f"article {article_id} not found")
        metas = await sources.get_sources_meta(uow, {row["source_id"]})
    events, enr = await _event_ids(request, [article_id]), await _enrichment(request, [article_id])
    return ArticleDetail(
        **_item(row, metas, events, enr),
        lead=row["lead"],
        author=row["author"],
        language=row["language"],
        duplicate_of=row["duplicate_of"],
        enrichment=None,
    )
