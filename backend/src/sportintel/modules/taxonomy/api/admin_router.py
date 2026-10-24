"""Админ-API справочников и очередь несвязанных упоминаний (BE-T4.9). Все действия — taxonomy.manage."""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import text

from sportintel.modules.audit import public as audit
from sportintel.modules.identity import public as identity
from sportintel.modules.taxonomy.domain.entity import Entity
from sportintel.modules.taxonomy.domain.values import EntityKind
from sportintel.modules.taxonomy.infrastructure.repository import SqlTaxonomyRepository
from sportintel.platform.errors import (
    ConcurrencyConflict,
    Conflict,
    FieldError,
    NotFound,
    ValidationFailed,
)
from sportintel.platform.http_api import etag, parse_if_match
from sportintel.platform.ids import new_id
from sportintel.platform.pagination import decode_cursor, encode_cursor
from sportintel.platform.text import normalize_name

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/taxonomy", tags=["taxonomy-admin"], route_class=identity.PermissionedRoute
)
Admin = Annotated[identity.CurrentUser, identity.require(P.TAXONOMY_MANAGE)]
PERM = identity.route_permission(P.TAXONOMY_MANAGE)


class DuplicateEntity(Conflict):
    code = "taxonomy.duplicate"
    title = "Entity already exists"


LOCALES = {"pt-BR", "en", "ru"}


def _check_names(v: dict[str, str] | None) -> dict[str, str] | None:
    if v is not None and not {k for k, x in v.items() if x.strip()} >= LOCALES:
        raise ValueError("name_i18n needs pt-BR, en and ru")
    return v


class SportCreate(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    name_i18n: Annotated[dict[str, str], AfterValidator(_check_names)]
    sort: int = 100


class SportPatch(BaseModel):
    name_i18n: Annotated[dict[str, str] | None, AfterValidator(_check_names)] = None
    sort: int | None = None
    active: bool | None = None


class EntityCreate(BaseModel):
    kind: EntityKind
    sport_id: str | None = None
    canonical_name: str = Field(min_length=1, max_length=200)
    country: str | None = None
    priority: int = Field(default=0, ge=-1, le=2)
    aliases: list[str] = Field(default_factory=list, max_length=50)


class EntityPatch(BaseModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=200)
    priority: int | None = Field(default=None, ge=-1, le=2)
    review_state: Literal["approved", "pending", "ignored"] | None = None
    active: bool | None = None
    sport_id: str | None = None
    # название для показа на языках интерфейса; пустое — показывается canonical_name
    name_i18n: dict[Literal["ru", "en"], str] | None = None


class EntityAdminItem(BaseModel):
    id: uuid.UUID
    kind: str
    sport_id: str | None
    canonical_name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    priority: int
    review_state: str
    active: bool
    aliases: list[str]
    auto_created: bool
    version: int


class EntityAdminPage(BaseModel):
    items: list[EntityAdminItem]
    next_cursor: str | None


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=200)


class UnlinkedItem(BaseModel):
    mention_norm: str
    mention: str
    kind: str
    sport_id: str | None
    sport_key: str
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    sample_article_id: uuid.UUID | None


class UnlinkedPage(BaseModel):
    items: list[UnlinkedItem]
    next_cursor: str | None


class ResolveRequest(BaseModel):
    kind: str
    sport_key: str = ""
    action: Literal["link", "create", "ignore"]
    entity_id: uuid.UUID | None = None
    canonical_name: str | None = None
    priority: int = Field(default=0, ge=-1, le=2)


async def _rec(
    uow: Any,
    user: identity.CurrentUser,
    action: audit.AuditAction,
    target_type: str,
    target_id: str,
    **kw: Any,
) -> None:
    await audit.record(
        uow, actor_id=user.id, action=action, target_type=target_type, target_id=target_id, **kw
    )


def _relink(uow: Any, mention_norm: str, entity_id: uuid.UUID) -> None:
    uow.enqueue_after_commit(
        "intelligence.relink_entities",
        queueing_lock=f"relink:{mention_norm}:{entity_id}",
        mention_norm=mention_norm,
        entity_id=str(entity_id),
    )


async def _entity_item(uow: Any, entity_id: uuid.UUID) -> EntityAdminItem:
    row = (
        await uow.session.execute(
            text(
                "SELECT e.*, coalesce(array_agg(a.alias ORDER BY a.alias) FILTER (WHERE a.alias IS NOT NULL), '{}') AS aliases"
                " FROM taxonomy.entities e LEFT JOIN taxonomy.entity_aliases a ON a.entity_id = e.id WHERE e.id = :i GROUP BY e.id"
            ),
            {"i": entity_id},
        )
    ).first()
    if row is None:
        raise NotFound(f"entity {entity_id} not found")
    return EntityAdminItem(
        **{k: v for k, v in row._mapping.items() if k in EntityAdminItem.model_fields}
    )


@router.post("/sports", status_code=201, openapi_extra=PERM)
async def create_sport(body: SportCreate, request: Request, user: Admin) -> SportCreate:
    async with request.app.state.db.uow() as uow:
        res = await uow.session.execute(
            text(
                "INSERT INTO taxonomy.sports (id, name_i18n, sort) VALUES (:i, CAST(:n AS jsonb), :s) ON CONFLICT DO NOTHING RETURNING id"
            ),
            {"i": body.id, "n": json.dumps(body.name_i18n), "s": body.sort},
        )
        if res.first() is None:
            raise DuplicateEntity(details=[FieldError("id", "duplicate", "sport already exists")])
        await _rec(
            uow,
            user,
            audit.AuditAction.TAXONOMY_SPORT_CREATED,
            "sport",
            body.id,
            after=body.model_dump(),
        )
    return body


@router.patch("/sports/{sport_id}", openapi_extra=PERM)
async def patch_sport(
    sport_id: str, body: SportPatch, request: Request, user: Admin
) -> dict[str, Any]:
    patch = {k: getattr(body, k) for k in body.model_fields_set if getattr(body, k) is not None}
    if not patch:
        raise ValidationFailed(details=[FieldError("body", "empty", "nothing to change")])
    sets = ", ".join(
        f"{k} = CAST(:{k} AS jsonb)" if k == "name_i18n" else f"{k} = :{k}" for k in patch
    )
    params = {
        **{k: (json.dumps(v) if k == "name_i18n" else v) for k, v in patch.items()},
        "id": sport_id,
    }
    async with request.app.state.db.uow() as uow:
        row = (
            await uow.session.execute(
                text(
                    f"UPDATE taxonomy.sports SET {sets} WHERE id = :id RETURNING id, name_i18n, sort, active"  # noqa: S608 — колонки из модели
                ),
                params,
            )
        ).first()
        if row is None:
            raise NotFound(f"sport {sport_id} not found")
        await _rec(
            uow, user, audit.AuditAction.TAXONOMY_SPORT_UPDATED, "sport", sport_id, after=patch
        )
    return dict(row._mapping)


@router.get("/entities/admin", openapi_extra=PERM)
async def list_entities_admin(
    request: Request,
    _: Admin,
    kind: EntityKind | None = None,
    sport: str | None = None,
    review_state: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EntityAdminPage:
    after = decode_cursor(cursor, [str, uuid.UUID]) if cursor else None
    params: dict[str, Any] = {
        "kind": kind.value if kind else None,
        "sport": sport,
        "rs": review_state,
        "k": limit + 1,
        "q": f"%{normalize_name(q)}%" if q else None,
        "an": after[0] if after else None,
        "ai": after[1] if after else None,
    }
    async with request.app.state.db.uow() as uow:
        rows = (
            await uow.session.execute(
                text(
                    "SELECT e.*, coalesce(array_agg(a.alias ORDER BY a.alias) FILTER (WHERE a.alias IS NOT NULL), '{}') AS aliases"
                    " FROM taxonomy.entities e LEFT JOIN taxonomy.entity_aliases a ON a.entity_id = e.id"
                    " WHERE (CAST(:kind AS text) IS NULL OR e.kind = :kind) AND (CAST(:sport AS text) IS NULL OR e.sport_id = :sport)"
                    " AND (CAST(:rs AS text) IS NULL OR e.review_state = :rs)"
                    " AND (CAST(:q AS text) IS NULL OR EXISTS (SELECT 1 FROM taxonomy.entity_aliases x WHERE x.entity_id = e.id AND x.alias_norm LIKE :q))"
                    " AND (CAST(:an AS text) IS NULL OR (e.name_norm, e.id) > (:an, CAST(:ai AS uuid)))"
                    " GROUP BY e.id ORDER BY e.name_norm, e.id LIMIT :k"
                ),
                params,
            )
        ).all()
    items = [
        EntityAdminItem(
            **{k: v for k, v in r._mapping.items() if k in EntityAdminItem.model_fields}
        )
        for r in rows[:limit]
    ]
    nxt = (
        encode_cursor([rows[limit - 1].name_norm, rows[limit - 1].id])
        if len(rows) > limit
        else None
    )
    return EntityAdminPage(items=items, next_cursor=nxt)


async def _create(
    uow: Any,
    kind: EntityKind,
    sport_id: str | None,
    name: str,
    priority: int,
    aliases: list[str],
    country: str | None = None,
) -> uuid.UUID:
    norm = normalize_name(name)
    dup = (
        await uow.session.execute(
            text(
                "SELECT 1 FROM taxonomy.entities WHERE kind = :k AND coalesce(sport_id, '') = coalesce(CAST(:s AS text), '') AND name_norm = :n"
            ),
            {"k": kind.value, "s": sport_id, "n": norm},
        )
    ).first()
    if dup:
        raise DuplicateEntity(
            details=[FieldError("canonical_name", "duplicate", "entity already exists")]
        )
    e = Entity(
        id=new_id(),
        kind=kind,
        sport_id=sport_id,
        canonical_name=name.strip(),
        name_norm=norm,
        country=country,
        priority=priority,
        aliases=aliases,
    )
    await SqlTaxonomyRepository(uow.session).add_entity(e)
    return e.id


@router.post("/entities", status_code=201, openapi_extra=PERM)
async def create_entity(
    body: EntityCreate, request: Request, response: Response, user: Admin
) -> EntityAdminItem:
    async with request.app.state.db.uow() as uow:
        eid = await _create(
            uow,
            body.kind,
            body.sport_id,
            body.canonical_name,
            body.priority,
            body.aliases,
            body.country,
        )
        for a in {normalize_name(x) for x in [body.canonical_name, *body.aliases] if x.strip()}:
            _relink(uow, a, eid)
        await _rec(
            uow,
            user,
            audit.AuditAction.TAXONOMY_ENTITY_CREATED,
            "entity",
            str(eid),
            after=body.model_dump(mode="json"),
        )
        item = await _entity_item(uow, eid)
    response.headers["ETag"] = etag(item.version)
    return item


@router.patch("/entities/{entity_id}", openapi_extra=PERM)
async def patch_entity(
    entity_id: uuid.UUID,
    body: EntityPatch,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Admin,
) -> EntityAdminItem:
    patch = {k: getattr(body, k) for k in body.model_fields_set}
    if not patch:
        raise ValidationFailed(details=[FieldError("body", "empty", "nothing to change")])
    if "canonical_name" in patch:
        patch["name_norm"] = normalize_name(patch["canonical_name"])
    if "name_i18n" in patch:
        clean = {k: v.strip() for k, v in (patch["name_i18n"] or {}).items() if v.strip()}
        patch["name_i18n"] = json.dumps(clean, ensure_ascii=False)
    sets = ", ".join(
        f"{k} = CAST(:{k} AS jsonb)" if k == "name_i18n" else f"{k} = :{k}" for k in patch
    )
    async with request.app.state.db.uow() as uow:
        res = await uow.session.execute(
            text(
                f"UPDATE taxonomy.entities SET {sets}, version = version + 1, updated_at = now()"  # noqa: S608 — колонки из модели
                " WHERE id = :id AND version = :v RETURNING id"
            ),
            {**patch, "id": entity_id, "v": expected_version},
        )
        if res.first() is None:
            if (
                await uow.session.execute(
                    text("SELECT 1 FROM taxonomy.entities WHERE id = :i"), {"i": entity_id}
                )
            ).first():
                raise ConcurrencyConflict(current=None)
            raise NotFound(f"entity {entity_id} not found")
        if "canonical_name" in patch:
            await SqlTaxonomyRepository(uow.session).add_aliases(
                entity_id, [patch["canonical_name"]]
            )
        await _rec(
            uow,
            user,
            audit.AuditAction.TAXONOMY_ENTITY_UPDATED,
            "entity",
            str(entity_id),
            after=patch,
        )
        item = await _entity_item(uow, entity_id)
    response.headers["ETag"] = etag(item.version)
    return item


@router.post("/entities/{entity_id}/aliases", openapi_extra=PERM)
async def add_alias(
    entity_id: uuid.UUID, body: AliasCreate, request: Request, user: Admin
) -> EntityAdminItem:
    async with request.app.state.db.uow() as uow:
        await _entity_item(uow, entity_id)
        await SqlTaxonomyRepository(uow.session).add_aliases(
            entity_id, [body.alias]
        )  # повтор идемпотентен
        _relink(uow, normalize_name(body.alias), entity_id)
        await _rec(
            uow,
            user,
            audit.AuditAction.TAXONOMY_ALIAS_ADDED,
            "entity",
            str(entity_id),
            after={"alias": body.alias},
        )
        return await _entity_item(uow, entity_id)


@router.delete("/entities/{entity_id}/aliases/{alias_norm}", openapi_extra=PERM)
async def remove_alias(
    entity_id: uuid.UUID, alias_norm: str, request: Request, user: Admin
) -> EntityAdminItem:
    async with request.app.state.db.uow() as uow:
        item = await _entity_item(uow, entity_id)
        if normalize_name(item.canonical_name) == alias_norm:
            raise ValidationFailed(
                details=[
                    FieldError("alias_norm", "canonical", "the canonical alias cannot be removed")
                ]
            )
        await uow.session.execute(
            text("DELETE FROM taxonomy.entity_aliases WHERE entity_id = :i AND alias_norm = :a"),
            {"i": entity_id, "a": alias_norm},
        )
        await _rec(
            uow,
            user,
            audit.AuditAction.TAXONOMY_ALIAS_REMOVED,
            "entity",
            str(entity_id),
            before={"alias_norm": alias_norm},
        )
        return await _entity_item(uow, entity_id)


@router.get("/unlinked", openapi_extra=PERM)
async def list_unlinked(
    request: Request,
    _: Admin,
    state: Literal["open", "resolved", "ignored"] = "open",
    kind: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> UnlinkedPage:
    after = decode_cursor(cursor, [int, str]) if cursor else None
    async with request.app.state.db.uow() as uow:
        rows = (
            await uow.session.execute(
                text(
                    "SELECT * FROM taxonomy.unlinked_mentions WHERE state = :st AND (CAST(:kind AS text) IS NULL OR kind = :kind)"
                    " AND (CAST(:o AS int) IS NULL OR (occurrences, mention_norm) < (:o, :m))"
                    " ORDER BY occurrences DESC, mention_norm DESC LIMIT :k"
                ),
                {
                    "st": state,
                    "kind": kind,
                    "o": after[0] if after else None,
                    "m": after[1] if after else None,
                    "k": limit + 1,
                },
            )
        ).all()
    items = [
        UnlinkedItem(**{k: v for k, v in r._mapping.items() if k in UnlinkedItem.model_fields})
        for r in rows[:limit]
    ]
    nxt = (
        encode_cursor([rows[limit - 1].occurrences, rows[limit - 1].mention_norm])
        if len(rows) > limit
        else None
    )
    return UnlinkedPage(items=items, next_cursor=nxt)


@router.post("/unlinked/{mention_norm}:resolve", openapi_extra=PERM)
async def resolve_unlinked(
    mention_norm: str, body: ResolveRequest, request: Request, user: Admin
) -> dict[str, Any]:
    key = {"m": mention_norm, "k": body.kind, "s": body.sport_key}
    async with request.app.state.db.uow() as uow:
        row = (
            await uow.session.execute(
                text(
                    "SELECT * FROM taxonomy.unlinked_mentions WHERE mention_norm = :m AND kind = :k AND sport_key = :s FOR UPDATE"
                ),
                key,
            )
        ).first()
        if row is None:
            raise NotFound(f"unlinked mention {mention_norm} not found")
        entity_id: uuid.UUID | None = None
        if body.action == "link":
            if body.entity_id is None:
                raise ValidationFailed(
                    details=[FieldError("entity_id", "required", "entity_id is required for link")]
                )
            await _entity_item(uow, body.entity_id)
            await SqlTaxonomyRepository(uow.session).add_aliases(body.entity_id, [row.mention])
            entity_id = body.entity_id
        elif body.action == "create":
            entity_id = await _create(
                uow,
                EntityKind(body.kind),
                row.sport_id,
                body.canonical_name or row.mention,
                body.priority,
                [row.mention],
            )
        state = "ignored" if body.action == "ignore" else "resolved"
        await uow.session.execute(
            text(
                "UPDATE taxonomy.unlinked_mentions SET state = :st WHERE mention_norm = :m AND kind = :k AND sport_key = :s"
            ),
            {**key, "st": state},
        )
        if entity_id:
            _relink(uow, mention_norm, entity_id)
        await _rec(
            uow,
            user,
            audit.AuditAction.TAXONOMY_UNLINKED_RESOLVED,
            "unlinked",
            mention_norm,
            after={"action": body.action, "entity_id": str(entity_id) if entity_id else None},
        )
    return {"state": state, "entity_id": entity_id}
