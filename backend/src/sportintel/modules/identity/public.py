"""Публичный фасад модуля. Другие модули импортируют только отсюда.

Связывание слоёв: application не видит infrastructure (import-linter), поэтому фасад
подставляет SQL-хранилища в use case и отдаёт наружу сигнатуры из спецификаций.
"""

import uuid
from collections.abc import Awaitable, Callable, Collection
from typing import Any

from sportintel.modules.identity.api.cookies import cookie_name
from sportintel.modules.identity.api.deps import current_user, optional_user
from sportintel.modules.identity.api.me import dev_router
from sportintel.modules.identity.api.me import router as me_router
from sportintel.modules.identity.api.rbac import (
    PermissionedRoute,
    declared_permission,
    require,
    route_permission,
)
from sportintel.modules.identity.api.router import router
from sportintel.modules.identity.application import sessions as _sessions
from sportintel.modules.identity.application.ports import OidcProvider
from sportintel.modules.identity.application.sessions import CurrentUser
from sportintel.modules.identity.domain.password import hash_password, password_problem
from sportintel.modules.identity.domain.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    has_permission,
)
from sportintel.modules.identity.domain.session import SessionRecord
from sportintel.modules.identity.domain.user import DEFAULT_TIMEZONE, User
from sportintel.modules.identity.domain.values import Locale, Role
from sportintel.modules.identity.infrastructure.oidc_fake import FakeOidcProvider
from sportintel.modules.identity.infrastructure.oidc_google import DiscoveryOidcProvider
from sportintel.modules.identity.infrastructure.repository import SqlSessionStore, SqlUserRepository
from sportintel.platform.clock import Clock
from sportintel.platform.config import Settings
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.errors import FieldError, ValidationFailed
from sportintel.platform.ids import new_id

__all__ = [
    "ROLE_PERMISSIONS",
    "CurrentUser",
    "Locale",
    "OidcProvider",
    "Permission",
    "PermissionedRoute",
    "Role",
    "SessionRecord",
    "User",
    "build_oidc_provider",
    "cookie_name",
    "create_session",
    "csrf_resolver",
    "current_user",
    "declared_permission",
    "dev_router",
    "ensure_initial_admin",
    "has_permission",
    "me_router",
    "optional_user",
    "require",
    "resolve_session",
    "revoke_all_for_user",
    "revoke_session",
    "route_permission",
    "router",
    "set_password",
    "user_names",
    "users_router",
]


def _store(uow: UnitOfWork) -> SqlSessionStore:
    return SqlSessionStore(uow.session)


async def create_session(
    uow: UnitOfWork, user_id: uuid.UUID, ip: str | None, user_agent: str | None, clock: Clock
) -> tuple[str, SessionRecord]:
    return await _sessions.create_session(uow, _store(uow), user_id, ip, user_agent, clock)


async def resolve_session(db: Database, token: str, clock: Clock) -> CurrentUser | None:
    return await _sessions.resolve_session(db, _store, token, clock)


async def revoke_session(uow: UnitOfWork, token: str) -> None:
    await _sessions.revoke_session(_store(uow), token)


async def revoke_all_for_user(uow: UnitOfWork, user_id: uuid.UUID) -> int:
    return await _sessions.revoke_all_for_user(_store(uow), user_id)


async def set_password(
    uow: UnitOfWork, email: str, password: str, clock: Clock, *, role: Role | None = None
) -> User:
    """Задать пароль пользователю по e-mail; нет такого — создать (с role, иначе researcher).

    role — повысить/понизить заодно (первый admin). Пароль проверяется по длине.
    """
    if problem := password_problem(password):
        raise ValidationFailed(details=[FieldError("password", problem, "password rejected")])
    users = SqlUserRepository(uow.session)
    now = clock.now()
    user = await users.find_by_email(email)
    if user is None:
        user = User(
            id=new_id(),
            email=email,
            display_name=email.split("@", 1)[0],
            role=role or Role.RESEARCHER,
            locale=Locale.RU,
            timezone=DEFAULT_TIMEZONE,
            hotkeys_enabled=True,
            active=True,
            invited=False,
            oidc_subject=None,
            last_login_at=None,
            version=1,
        )
        await users.insert(user)
    elif role is not None and (user.role != role or not user.active):
        user = await users.set_role_and_login(user.id, role, now)
    await users.set_password(user.id, hash_password(password), now)
    return user


async def ensure_initial_admin(db: Database, settings: Settings, clock: Clock) -> bool:
    """Старт web: BOOTSTRAP_ADMIN_EMAIL + INITIAL_ADMIN_PASSWORD → admin, пока активного admin нет.

    Идемпотентно: при живом admin ничего не делает (пароль из env не перезаписывает
    сменённый). Advisory lock — две реплики web не создадут двух admin. True — создан.
    """
    email, password = settings.bootstrap_admin_email, settings.initial_admin_password
    if not (email and password):
        return False
    async with db.uow() as uow:
        await uow.advisory_xact_lock("identity:admins")
        if await SqlUserRepository(uow.session).any_active_admin():
            return False
        await set_password(uow, email, password.get_secret_value(), clock, role=Role.ADMIN)
    return True


_FAKE_IDP_ENVS = {"local", "ci", "e2e"}


def build_oidc_provider(settings: Settings) -> OidcProvider | None:
    """local/ci/e2e → fake (без сети); иначе — реальный IdP по discovery, если OIDC_* заданы.

    None — вход через IdP выключен, остаётся вход по паролю (BE-T0.15 §6).
    """
    if settings.env in _FAKE_IDP_ENVS:
        return FakeOidcProvider()
    if not (settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret):
        return None  # Settings уже проверил, что OIDC_* заданы либо все, либо ни одной
    return DiscoveryOidcProvider(
        settings.oidc_issuer,
        settings.oidc_client_id,
        settings.oidc_client_secret.get_secret_value(),
        frozenset(settings.oidc_allowed_domains),
    )


def csrf_resolver(state: Any) -> Callable[[str], Awaitable[str | None]]:
    """Для platform.http_api.CsrfMiddleware: токен сессии → её csrf_token.

    `state` — app.state; db и clock читаются при каждом вызове (тесты подменяют db).
    """

    async def resolve(token: str) -> str | None:
        user = await _sessions.resolve_session(state.db, _store, token, state.clock)
        return user.csrf_token if user else None

    return resolve


async def user_names(uow: UnitOfWork, ids: "Collection[uuid.UUID]") -> dict[uuid.UUID, str]:
    """Имена для истории действий (BE-T4.7)."""
    from sqlalchemy import text

    if not ids:
        return {}
    rows = await uow.session.execute(
        text("SELECT id, display_name FROM identity.users WHERE id = ANY(:ids)"), {"ids": list(ids)}
    )
    return {i: n for i, n in rows}


from sportintel.modules.identity.api.users_router import router as users_router  # noqa: E402
