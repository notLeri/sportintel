"""`/auth/*` — вход через OIDC и выход (BE-T0.15 §9)."""

import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from sportintel.modules.audit import public as audit
from sportintel.modules.identity.api.cookies import (
    clear_session_cookie,
    session_token,
    set_session_cookie,
)
from sportintel.modules.identity.api.me import MeResponse, me_response, ui_locale
from sportintel.modules.identity.api.rbac import PermissionedRoute, route_permission
from sportintel.modules.identity.api.schemas import LogoutResponse
from sportintel.modules.identity.application.login import (
    TX_TTL,
    AccessDenied,
    LoginConfig,
    complete_login,
    consume_transaction,
    start_login,
)
from sportintel.modules.identity.application.ports import OidcError, OidcProvider
from sportintel.modules.identity.application.sessions import (
    POLICY,
    create_session,
    resolve_session,
    revoke_session,
    to_current_user,
)
from sportintel.modules.identity.domain.password import MAX_LENGTH, verify_password
from sportintel.modules.identity.infrastructure.repository import (
    SqlOidcTxStore,
    SqlSessionStore,
    SqlUserRepository,
)
from sportintel.platform.clock import Clock
from sportintel.platform.config import Settings
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.errors import RateLimited, Unauthenticated

router = APIRouter(prefix="/auth", tags=["auth"], route_class=PermissionedRoute)
PUBLIC = route_permission("public")
TX_COOKIE = "oidc_tx"
_INSECURE_ENVS = {"local", "e2e"}
_log = structlog.get_logger("sportintel.identity")


@dataclass(frozen=True)
class AuthContext:
    db: Database
    settings: Settings
    clock: Clock
    oidc: OidcProvider | None  # None — OIDC_* не заданы, вход только по паролю

    @property
    def redirect_uri(self) -> str:
        # Строгое совпадение с зарегистрированным в IdP (BE-T0.15 §15).
        return f"{self.settings.app_base_url.rstrip('/')}/auth/callback"


def _ctx(request: Request) -> AuthContext:
    s = request.app.state
    return AuthContext(db=s.db, settings=s.settings, clock=s.clock, oidc=s.oidc)


def _store(uow: UnitOfWork) -> SqlSessionStore:
    return SqlSessionStore(uow.session)


def _to_login(error: str, env: str) -> RedirectResponse:
    response = RedirectResponse(f"/login?{urlencode({'error': error})}", status_code=302)
    response.delete_cookie(TX_COOKIE, path="/auth", secure=env not in _INSECURE_ENVS)
    return response


@router.get("/login", openapi_extra=PUBLIC, status_code=302, response_class=RedirectResponse)
async def login(request: Request, next: str | None = None) -> RedirectResponse:
    ctx = _ctx(request)
    if ctx.oidc is None:
        return _to_login("auth.oidc_disabled", ctx.settings.env)
    try:
        async with ctx.db.uow() as uow:
            tx_id, url = await start_login(
                SqlOidcTxStore(uow.session), ctx.oidc, next, ctx.redirect_uri, ctx.clock
            )
    except OidcError:
        _log.warning("identity.oidc_unavailable", stage="authorize")
        return _to_login("auth.oidc_failed", ctx.settings.env)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        TX_COOKIE,
        tx_id,
        max_age=int(TX_TTL.total_seconds()),
        path="/auth",
        secure=ctx.settings.env not in _INSECURE_ENVS,
        httponly=True,
        samesite="lax",  # Strict не отправится при редиректе с IdP (§22)
    )
    return response


@router.get("/callback", openapi_extra=PUBLIC, status_code=302, response_class=RedirectResponse)
async def callback(
    request: Request, code: str | None = None, state: str | None = None, error: str | None = None
) -> RedirectResponse:
    ctx = _ctx(request)
    env = ctx.settings.env
    if ctx.oidc is None:
        return _to_login("auth.oidc_disabled", env)
    if error:
        _log.info("identity.oidc_error_returned", error=error[:64])
        return _to_login("auth.oidc_failed", env)

    async with ctx.db.uow() as uow:  # транзакция удаляется при любом исходе
        tx = await consume_transaction(
            SqlOidcTxStore(uow.session), request.cookies.get(TX_COOKIE), state, ctx.clock
        )
    if tx is None or not code:
        return _to_login("auth.state_mismatch", env)

    try:
        identity = await ctx.oidc.exchange_code(code, tx.code_verifier, ctx.redirect_uri, tx.nonce)
    except OidcError as e:
        _log.warning("identity.oidc_unavailable", stage="token", error=str(e))
        return _to_login("auth.oidc_failed", env)

    config = LoginConfig(
        allowed_domains=frozenset(ctx.settings.oidc_allowed_domains),
        bootstrap_admin_email=ctx.settings.bootstrap_admin_email,
    )
    client_ip = request.client.host if request.client else None
    try:
        async with ctx.db.uow() as uow:
            token, user = await complete_login(
                uow,
                SqlUserRepository(uow.session),
                _store(uow),
                identity,
                client_ip,
                request.headers.get("user-agent"),
                ctx.clock,
                config,
            )
            await audit.record(
                uow,
                actor_id=user.id,
                action=audit.AuditAction.AUTH_LOGIN,
                target_type="user",
                target_id=str(user.id),
            )
    except AccessDenied as e:
        # Отказ откатил транзакцию входа — аудит отказа пишется отдельно.
        async with ctx.db.uow() as uow:
            await audit.record(
                uow,
                actor_id=None,
                action=audit.AuditAction.AUTH_LOGIN_DENIED,
                target_type="email",
                target_id=identity.email.lower(),
                reason=str(e.code),
            )
        return _to_login(e.code, env)

    now = ctx.clock.now()
    response = RedirectResponse(tx.next_path, status_code=302)
    set_session_cookie(response, token, now + POLICY.absolute, now, env)
    response.delete_cookie(TX_COOKIE, path="/auth", secure=env not in _INSECURE_ENVS)
    return response


@router.post("/logout", openapi_extra=PUBLIC, response_model=LogoutResponse)
async def logout(request: Request) -> JSONResponse:
    ctx = _ctx(request)
    token = session_token(request, ctx.settings.env)
    current = await resolve_session(ctx.db, _store, token, ctx.clock) if token else None
    if token is None or current is None:
        raise Unauthenticated()
    # CSRF проверил CsrfMiddleware (BE-T0.16).
    async with ctx.db.uow() as uow:
        await revoke_session(_store(uow), token)
        await audit.record(
            uow,
            actor_id=current.id,
            action=audit.AuditAction.AUTH_LOGOUT,
            target_type="user",
            target_id=str(current.id),
        )
    _log.info("identity.logout", user_id=str(current.id))
    body = LogoutResponse(logout_url=await ctx.oidc.end_session_url() if ctx.oidc else None)
    response = JSONResponse(body.model_dump())
    clear_session_cookie(response, ctx.settings.env)
    return response


# --- вход по паролю ---

LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_S = 15 * 60


class _Attempts:
    """Неудачные входы по ключу «email|ip» за скользящее окно.

    ponytail: память одного процесса web; при нескольких репликах web — счётчик в БД.
    """

    def __init__(self) -> None:
        self._fails: dict[str, deque[float]] = {}

    def retry_after(self, key: str) -> int:
        q = self._fails.get(key)
        now = time.monotonic()
        while q and now - q[0] > LOGIN_WINDOW_S:
            q.popleft()
        if not q or len(q) < LOGIN_ATTEMPTS:
            return 0
        return max(1, int(LOGIN_WINDOW_S - (now - q[0])))

    def fail(self, key: str) -> None:
        if len(self._fails) > 10_000:  # защита памяти от перебора по множеству email
            self._fails.clear()
        self._fails.setdefault(key, deque()).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)

    def reset_all(self) -> None:
        self._fails.clear()


ATTEMPTS = _Attempts()


class PasswordLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=MAX_LENGTH)


class BadCredentials(Unauthenticated):
    code = "auth.bad_credentials"
    title = "Wrong e-mail or password"


@router.post("/password-login", openapi_extra=PUBLIC, response_model=MeResponse)
async def password_login(body: PasswordLoginRequest, request: Request) -> JSONResponse:
    """Sign in with e-mail and password: always available, including without OIDC (response as in GET /me)."""
    ctx = _ctx(request)
    email = body.email.strip().lower()
    client_ip = request.client.host if request.client else None
    key = f"{email}|{client_ip}"
    if wait := ATTEMPTS.retry_after(key):
        raise RateLimited(retry_after_s=wait)
    async with ctx.db.uow() as uow:
        users = SqlUserRepository(uow.session)
        found = await users.find_with_password(email)
        # Хэш считается и для несуществующего e-mail: время ответа не выдаёт, есть ли такой пользователь.
        valid = verify_password(body.password, found[1] if found else _DUMMY_HASH)
        user = found[0] if found and valid and found[0].active else None
        if user is None:
            ATTEMPTS.fail(key)
            await audit.record(
                uow,
                actor_id=None,
                action=audit.AuditAction.AUTH_LOGIN_DENIED,
                target_type="email",
                target_id=email,
                reason="auth.bad_credentials",
            )
            _log.info("identity.password_login_denied")
        else:
            now = ctx.clock.now()
            await users.touch_login(user.id, now)
            token, record = await create_session(
                uow, _store(uow), user.id, client_ip, request.headers.get("user-agent"), ctx.clock
            )
            await audit.record(
                uow,
                actor_id=user.id,
                action=audit.AuditAction.AUTH_LOGIN,
                target_type="user",
                target_id=str(user.id),
            )
    if user is None:  # аудит отказа уже закоммичен
        raise BadCredentials()
    ATTEMPTS.reset(key)
    _log.info("identity.login_succeeded", user_id=str(user.id), method="password")
    response = JSONResponse(
        me_response(
            to_current_user(user, record), request, locale=await ui_locale(request)
        ).model_dump(mode="json")
    )
    set_session_cookie(response, token, record.absolute_expires_at, now, ctx.settings.env)
    return response


_DUMMY_HASH = (
    "scrypt$16384$8$1$00000000000000000000000000000000$"
    "0000000000000000000000000000000000000000000000000000000000000000"
)
