"""`GET /api/v1/me` и `POST /auth/dev-login` (BE-T0.16)."""

import uuid
from dataclasses import replace
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, field_validator
from sqlalchemy import text

from sportintel.modules.identity.api.cookies import set_session_cookie
from sportintel.modules.identity.api.deps import session_store
from sportintel.modules.identity.api.rbac import PermissionedRoute, require, route_permission
from sportintel.modules.identity.application.sessions import (
    CurrentUser,
    create_session,
    to_current_user,
)
from sportintel.modules.identity.application.sessions import clear_cache as clear_session_cache
from sportintel.modules.identity.domain.permissions import Permission, permissions_for
from sportintel.modules.identity.domain.user import DEFAULT_TIMEZONE, User
from sportintel.modules.identity.domain.values import Locale, Role
from sportintel.modules.identity.infrastructure.repository import SqlUserRepository
from sportintel.platform import settings_store
from sportintel.platform.flags import all_flags
from sportintel.platform.ids import new_id

router = APIRouter(prefix="/api/v1", tags=["identity"], route_class=PermissionedRoute)
dev_router = APIRouter(prefix="/auth", tags=["auth"], route_class=PermissionedRoute)


class TransitionOption(BaseModel):
    to: str
    min_role: Role


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    locale: Locale
    timezone: str
    hotkeys_enabled: bool
    csrf_token: str
    permissions: list[Permission]
    allowed_transitions: dict[str, list[TransitionOption]]  # BE-T3.2; до этого {}
    flags: dict[str, bool]
    system_status: dict[str, Any] | None  # BE-T4.14; до этого null


async def ui_locale(request: Request) -> Locale:
    """Язык интерфейса — общая настройка админа (languages.ui_language), а не личный выбор."""
    langs: Any = await settings_store.get(request.app.state.db, "languages")
    return Locale(langs.ui_language)


def me_response(
    user: CurrentUser,
    request: Request | None = None,
    system_status: dict[str, Any] | None = None,
    locale: Locale | None = None,
) -> MeResponse:
    # allowed_transitions даёт events через composition root (identity не импортирует events).
    transitions = getattr(request.app.state, "allowed_transitions_for", None) if request else None
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=Role(user.role),
        locale=locale or Locale(user.locale),
        timezone=user.timezone,
        hotkeys_enabled=user.hotkeys_enabled,
        csrf_token=user.csrf_token,
        permissions=sorted(permissions_for(user.role)),
        allowed_transitions=transitions(user.role) if transitions else {},
        flags=all_flags(),
        system_status=system_status,
    )


@router.get("/me", openapi_extra=route_permission(Permission.SELF_READ))
async def get_me(
    request: Request, user: Annotated[CurrentUser, require(Permission.SELF_READ)]
) -> MeResponse:
    # system_status собирает composition root (identity не знает о других модулях).
    fn = getattr(request.app.state, "system_status", None)
    return me_response(user, request, await fn() if fn else None, await ui_locale(request))


class MePatch(BaseModel):
    locale: Locale | None = None
    timezone: str | None = None
    hotkeys_enabled: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("unknown IANA timezone") from None
        return v


@router.patch("/me", openapi_extra=route_permission(Permission.SELF_READ))
async def patch_me(
    body: MePatch, request: Request, user: Annotated[CurrentUser, require(Permission.SELF_READ)]
) -> MeResponse:
    """Предпочтения пользователя (BE-T5.3): язык, часовой пояс, горячие клавиши."""
    patch = {
        k: (v.value if isinstance(v, Locale) else v)
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None
    }
    if patch:
        async with request.app.state.db.uow() as uow:
            sets = ", ".join(f"{k} = :{k}" for k in patch)
            await uow.session.execute(
                text(
                    f"UPDATE identity.users SET {sets}, version = version + 1, updated_at = now() WHERE id = :id"  # noqa: S608 — колонки из модели
                ),
                {**patch, "id": user.id},
            )
        clear_session_cache()  # ponytail: сброс всего кэша процесса; по ключу сессии — если пользователей станет много
        user = replace(user, **patch)  # type: ignore[arg-type]
    fn = getattr(request.app.state, "system_status", None)
    return me_response(user, request, await fn() if fn else None, await ui_locale(request))


def _dev_email(value: str) -> str:
    # test_environment: e2e-пользователи живут на зарезервированном домене *.test (BE-T5.1).
    try:
        return validate_email(value, check_deliverability=False, test_environment=True).normalized
    except EmailNotValidError as e:
        raise ValueError(str(e)) from None


class DevLoginRequest(BaseModel):
    email: Annotated[str, AfterValidator(_dev_email)]
    role: Role


@dev_router.post("/dev-login", openapi_extra=route_permission("public"), response_model=MeResponse)
async def dev_login(body: DevLoginRequest, request: Request) -> JSONResponse:
    """Только local/e2e: вход без IdP. Маршрут регистрируется условно (main.py)."""
    state = request.app.state
    now = state.clock.now()
    async with state.db.uow() as uow:
        users = SqlUserRepository(uow.session)
        user = await users.find_by_email(str(body.email))
        if user is None:
            user = User(
                id=new_id(),
                email=str(body.email),
                display_name=str(body.email).split("@", 1)[0],
                role=body.role,
                locale=Locale.RU,
                timezone=DEFAULT_TIMEZONE,
                hotkeys_enabled=True,
                active=True,
                invited=False,
                oidc_subject=None,
                last_login_at=now,
                version=1,
            )
            await users.insert(user)
        else:
            user = await users.set_role_and_login(user.id, body.role, now)
        token, record = await create_session(
            uow, session_store(uow), user.id, None, request.headers.get("user-agent"), state.clock
        )
    response = JSONResponse(
        me_response(
            to_current_user(user, record), request, locale=await ui_locale(request)
        ).model_dump(mode="json")
    )
    set_session_cookie(response, token, record.absolute_expires_at, now, state.settings.env)
    return response
