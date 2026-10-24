"""`/api/v1/sources` — управление источниками (BE-T1.2)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from sportintel.modules.audit import public as audit
from sportintel.modules.identity import public as identity
from sportintel.modules.sources.api.schemas import (
    FetchRunItem,
    FetchRunPage,
    SourceAdminItem,
    SourceAdminList,
    SourceBrief,
    SourceBriefList,
    SourceCreate,
    SourceDetail,
    SourceUpdate,
)
from sportintel.modules.sources.application import commands
from sportintel.modules.sources.infrastructure.repository import (
    SqlFetchRunStore,
    SqlSourceRepository,
)
from sportintel.platform.errors import ConcurrencyConflict, Forbidden, NotFound
from sportintel.platform.http_api import decode_cursor, encode_cursor, etag, parse_if_match

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/sources", tags=["sources"], route_class=identity.PermissionedRoute
)
CurrentUser = identity.CurrentUser


def _known_profiles(request: Request) -> frozenset[str]:
    # Профили знает ingestion; main.py кладёт провайдер в app.state (BE-T1.8 §6).
    provider = getattr(request.app.state, "known_parser_profiles", None)
    return frozenset(provider()) if provider else frozenset({"default"})


def _with_etag(response: Response, detail: SourceDetail) -> SourceDetail:
    response.headers["ETag"] = etag(detail.version)
    return detail


@router.get("", openapi_extra=identity.route_permission(P.SOURCES_READ))
async def list_sources(
    request: Request,
    user: Annotated[CurrentUser, identity.require(P.SOURCES_READ)],
    view: Literal["brief", "admin"] = "brief",
) -> SourceBriefList | SourceAdminList:
    if view == "admin" and not identity.has_permission(user.role, P.SOURCES_MANAGE):
        raise Forbidden()
    async with request.app.state.db.uow() as uow:
        rows = await SqlSourceRepository(uow.session).list()
    if view == "admin":
        # articles_24h даёт composition root: sources не читает статьи (BE-T4.8).
        counts_fn = getattr(request.app.state, "articles_24h", None)
        counts = await counts_fn() if counts_fn else {}
        return SourceAdminList(
            items=[
                SourceAdminItem.of(s).model_copy(
                    update={"articles_24h": counts.get(s.id, 0) if counts_fn else None}
                )
                for s in rows
            ]
        )
    return SourceBriefList(items=[SourceBrief.of(s) for s in rows])


@router.post("", status_code=201, openapi_extra=identity.route_permission(P.SOURCES_MANAGE))
async def create_source(
    body: SourceCreate,
    request: Request,
    response: Response,
    user: Annotated[CurrentUser, identity.require(P.SOURCES_MANAGE)],
) -> SourceDetail:
    now = request.app.state.clock.now()
    async with request.app.state.db.uow() as uow:
        source = await commands.create_source(
            SqlSourceRepository(uow.session), body.model_dump(), now, _known_profiles(request)
        )
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.SOURCE_CREATED,
            target_type="source",
            target_id=str(source.id),
            after=body.model_dump(),
        )
    return _with_etag(response, SourceDetail.of(source))


@router.get("/{source_id}", openapi_extra=identity.route_permission(P.SOURCES_MANAGE))
async def get_source(
    source_id: uuid.UUID,
    request: Request,
    response: Response,
    _: Annotated[CurrentUser, identity.require(P.SOURCES_MANAGE)],
) -> SourceDetail:
    async with request.app.state.db.uow() as uow:
        source = await SqlSourceRepository(uow.session).get(source_id)
    if source is None:
        raise NotFound(f"source {source_id} not found")
    return _with_etag(response, SourceDetail.of(source))


@router.patch("/{source_id}", openapi_extra=identity.route_permission(P.SOURCES_MANAGE))
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Annotated[CurrentUser, identity.require(P.SOURCES_MANAGE)],
) -> SourceDetail:
    patch = {name: getattr(body, name) for name in body.model_fields_set}
    now = request.app.state.clock.now()
    try:
        async with request.app.state.db.uow() as uow:
            source = await commands.update_source(
                SqlSourceRepository(uow.session),
                source_id,
                patch,
                expected_version,
                now,
                _known_profiles(request),
            )
            await audit.record(
                uow,
                actor_id=user.id,
                action=audit.AuditAction.SOURCE_UPDATED,
                target_type="source",
                target_id=str(source_id),
                after=patch,
            )
    except ConcurrencyConflict:
        # 412 с актуальным представлением ресурса (CONV §5.1)
        async with request.app.state.db.uow() as uow:
            latest = await SqlSourceRepository(uow.session).get(source_id)
        raise ConcurrencyConflict(
            current=SourceDetail.of(latest).model_dump(mode="json") if latest else None
        ) from None
    return _with_etag(response, SourceDetail.of(source))


@router.get("/{source_id}/runs", openapi_extra=identity.route_permission(P.SOURCES_MANAGE))
async def list_runs(
    source_id: uuid.UUID,
    request: Request,
    _: Annotated[CurrentUser, identity.require(P.SOURCES_MANAGE)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> FetchRunPage:
    after = None
    if cursor:
        started, run_id = decode_cursor(cursor, 2)
        try:
            after = (datetime.fromisoformat(str(started)), uuid.UUID(str(run_id)))
        except ValueError:
            decode_cursor("", 2)  # единый ответ 422 для испорченного cursor
    async with request.app.state.db.uow() as uow:
        if await SqlSourceRepository(uow.session).get(source_id) is None:
            raise NotFound(f"source {source_id} not found")
        rows = await SqlFetchRunStore(uow.session).page(source_id, after, limit + 1)
    page = rows[:limit]
    next_cursor = (
        encode_cursor((page[-1].started_at.isoformat(), str(page[-1].id)))
        if len(rows) > limit
        else None
    )
    return FetchRunPage(
        items=[
            FetchRunItem(**{k: v for k, v in r.__dict__.items() if k != "source_id"}) for r in page
        ],
        next_cursor=next_cursor,
    )
