"""Управление пользователями (BE-T4.11), право users.manage."""

# ruff: noqa: S608 — в SQL подставляются только константы и имена колонок из pydantic-модели

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import text

from sportintel.modules.audit import public as audit
from sportintel.modules.identity.api.me import _dev_email
from sportintel.modules.identity.api.rbac import PermissionedRoute, require, route_permission
from sportintel.modules.identity.application import sessions as _sessions
from sportintel.modules.identity.application.sessions import CurrentUser
from sportintel.modules.identity.domain.password import MAX_LENGTH, MIN_LENGTH, hash_password
from sportintel.modules.identity.domain.permissions import Permission
from sportintel.modules.identity.domain.values import Role
from sportintel.modules.identity.infrastructure.repository import SqlSessionStore
from sportintel.platform.errors import (
    ConcurrencyConflict,
    Conflict,
    FieldError,
    NotFound,
    ValidationFailed,
)
from sportintel.platform.http_api import etag, parse_if_match
from sportintel.platform.ids import new_id

router = APIRouter(prefix="/api/v1/users", tags=["users"], route_class=PermissionedRoute)
PERM = route_permission(Permission.USERS_MANAGE)
Admin = Annotated[CurrentUser, require(Permission.USERS_MANAGE)]
COLS = (
    "id, email, display_name, role, active, invited, last_login_at, created_at, version,"
    " password_hash IS NOT NULL AS has_password"
)
Password = Annotated[str, Field(min_length=MIN_LENGTH, max_length=MAX_LENGTH)]


class EmailExists(Conflict):
    code = "user.email_exists"
    title = "User with this email already exists"


class LastAdmin(Conflict):
    code = "user.last_admin"
    title = "The last active admin cannot be demoted or deactivated"


class UserAdminItem(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    active: bool
    invited: bool
    last_login_at: datetime | None
    created_at: datetime
    version: int
    has_password: bool  # можно войти по паролю


class UserList(BaseModel):
    items: list[UserAdminItem]


class UserCreate(BaseModel):
    email: Annotated[str, AfterValidator(_dev_email)]
    role: Role
    display_name: str | None = Field(default=None, max_length=200)
    password: Password | None = None  # временный пароль; без него — только вход через OIDC


class UserPatch(BaseModel):
    role: Role | None = None
    active: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: Password | None = None  # сброс пароля: сессии пользователя закрываются


async def _get(uow: Any, user_id: uuid.UUID) -> UserAdminItem:
    row = (
        await uow.session.execute(
            text(f"SELECT {COLS} FROM identity.users WHERE id = :i"), {"i": user_id}
        )
    ).first()
    if row is None:
        raise NotFound(f"user {user_id} not found")
    return UserAdminItem(**row._mapping)


@router.get("", openapi_extra=PERM)
async def list_users(
    request: Request, _: Admin, active: bool | None = None, q: str | None = None
) -> UserList:
    async with request.app.state.db.uow() as uow:
        rows = await uow.session.execute(
            text(
                f"SELECT {COLS} FROM identity.users WHERE (CAST(:a AS boolean) IS NULL OR active = :a)"
                " AND (CAST(:q AS text) IS NULL OR email ILIKE :q OR display_name ILIKE :q) ORDER BY email"
            ),
            {"a": active, "q": f"%{q.strip()}%" if q and q.strip() else None},
        )
        return UserList(items=[UserAdminItem(**r._mapping) for r in rows])


@router.post("", status_code=201, openapi_extra=PERM)
async def invite_user(
    body: UserCreate, request: Request, response: Response, user: Admin
) -> UserAdminItem:
    async with request.app.state.db.uow() as uow:
        res = await uow.session.execute(
            text(
                "INSERT INTO identity.users (id, email, display_name, role, invited, password_hash)"
                " VALUES (:i, :e, :n, :r, true, :p) ON CONFLICT (email) DO NOTHING RETURNING id"
            ),
            {
                "i": new_id(),
                "e": body.email,
                "n": body.display_name or body.email.split("@", 1)[0],
                "r": body.role.value,
                "p": hash_password(body.password) if body.password else None,
            },
        )
        uid = res.scalar()
        if uid is None:
            raise EmailExists()
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.USER_CREATED,
            target_type="user",
            target_id=str(uid),
            after=body.model_dump(mode="json", exclude={"password"})
            | {"has_password": bool(body.password)},
        )
        item = await _get(uow, uid)
    response.headers["ETag"] = etag(item.version)
    return item


@router.patch("/{user_id}", openapi_extra=PERM)
async def patch_user(
    user_id: uuid.UUID,
    body: UserPatch,
    request: Request,
    response: Response,
    expected_version: Annotated[int, Depends(parse_if_match)],
    user: Admin,
) -> UserAdminItem:
    patch = {k: getattr(body, k) for k in body.model_fields_set if getattr(body, k) is not None}
    password = patch.pop("password", None)
    if not patch and password is None:
        raise ValidationFailed(details=[FieldError("body", "empty", "nothing to change")])
    async with request.app.state.db.uow() as uow:
        await uow.advisory_xact_lock("identity:admins")  # проверка «последнего admin» без гонок
        cur = await _get(uow, user_id)
        if cur.version != expected_version:
            raise ConcurrencyConflict(current=None)
        losing_admin = (
            cur.role == Role.ADMIN
            and cur.active
            and (patch.get("active") is False or patch.get("role", Role.ADMIN) != Role.ADMIN)
        )
        if losing_admin:
            others = (
                await uow.session.execute(
                    text(
                        "SELECT count(*) FROM identity.users WHERE role = 'admin' AND active AND id <> :i"
                    ),
                    {"i": user_id},
                )
            ).scalar()
            if not others:
                raise LastAdmin()
        values = {k: (v.value if isinstance(v, Role) else v) for k, v in patch.items()}
        cols = {**values, **({"password_hash": hash_password(password)} if password else {})}
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        await uow.session.execute(
            text(
                f"UPDATE identity.users SET {sets}, version = version + 1, updated_at = now() WHERE id = :id"
            ),
            {**cols, "id": user_id},
        )
        if patch.get("active") is False or password:
            await _sessions.revoke_all_for_user(SqlSessionStore(uow.session), user_id)
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.USER_UPDATED,
            target_type="user",
            target_id=str(user_id),
            before={k: getattr(cur, k) for k in values},
            after=values | ({"password": "reset"} if password else {}),
        )
        item = await _get(uow, user_id)
    response.headers["ETag"] = etag(item.version)
    return item
