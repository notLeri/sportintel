"""`/api/v1/taxonomy` — справочники для UI (BE-T2.24)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel

from sportintel.modules.identity import public as identity
from sportintel.modules.taxonomy.domain.values import EntityKind
from sportintel.modules.taxonomy.infrastructure.repository import SqlTaxonomyRepository
from sportintel.platform import settings_store
from sportintel.platform.errors import FieldError, ValidationFailed
from sportintel.platform.pagination import split_multi
from sportintel.platform.text import normalize_name

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/taxonomy", tags=["taxonomy"], route_class=identity.PermissionedRoute
)


class SportItem(BaseModel):
    id: str
    name: str
    name_i18n: dict[str, str]
    sort: int


class SportList(BaseModel):
    items: list[SportItem]


class EntityItem(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    sport_id: str | None
    review_state: str


class EntityList(BaseModel):
    items: list[EntityItem]


@router.get("/sports", openapi_extra=identity.route_permission(P.TAXONOMY_READ))
async def sports(
    request: Request,
    response: Response,
    user: Annotated[identity.CurrentUser, identity.require(P.TAXONOMY_READ)],
) -> SportList:
    async with request.app.state.db.uow() as uow:
        rows = await SqlTaxonomyRepository(uow.session).list_sports(True)
    response.headers["Cache-Control"] = "private, max-age=300"
    return SportList(
        items=[
            SportItem(
                id=r["id"],
                name=r["name_i18n"].get(user.locale) or r["name_i18n"].get("en", r["id"]),
                name_i18n=r["name_i18n"],
                sort=r["sort"],
            )
            for r in sorted(rows, key=lambda r: r["sort"])
        ]
    )


def _item(r: Any, lang: str) -> EntityItem:
    return EntityItem(
        id=r.id,
        kind=str(r.kind),
        name=r.display(lang),
        sport_id=r.sport_id,
        review_state=str(r.review_state),
    )


@router.get("/entities", openapi_extra=identity.route_permission(P.TAXONOMY_READ))
async def entities(
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.TAXONOMY_READ)],
    q: str | None = None,
    kind: EntityKind | None = None,
    sport: str | None = None,
    ids: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> EntityList:
    from sportintel.modules.taxonomy import public as taxonomy

    async with request.app.state.db.uow() as uow:
        if ids:
            raw = split_multi(ids)
            if len(raw) > 50:
                raise ValidationFailed(details=[FieldError("ids", "too_many", "at most 50 ids")])
            try:
                wanted = [uuid.UUID(i) for i in raw]
            except ValueError:
                raise ValidationFailed(
                    details=[FieldError("ids", "invalid", "invalid UUID")]
                ) from None
        else:
            if len(normalize_name(q or "")) < 2:
                return EntityList(items=[])
            wanted = await taxonomy.search_entities(
                uow,
                q or "",
                limit=limit,
                threshold=0.3,
                kind=kind.value if kind else None,
                sport=sport,
                prefix=True,
            )
        got = await taxonomy.get_entities(uow, wanted)
        lang = await settings_store.ui_language(uow)
    return EntityList(
        items=[
            _item(got[i], lang)
            for i in wanted
            if i in got and str(got[i].review_state) != "ignored"
        ]
    )
