"""FastAPI-зависимости текущего пользователя (BE-T0.16)."""

from fastapi import Request

from sportintel.modules.identity.api.cookies import session_token
from sportintel.modules.identity.application.sessions import CurrentUser, resolve_session
from sportintel.modules.identity.infrastructure.repository import SqlSessionStore
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import Unauthenticated


def session_store(uow: UnitOfWork) -> SqlSessionStore:
    return SqlSessionStore(uow.session)


async def optional_user(request: Request) -> CurrentUser | None:
    cached: CurrentUser | None = getattr(request.state, "current_user", None)
    if cached is not None:
        return cached
    state = request.app.state
    token = session_token(request, state.settings.env)
    if not token:
        return None
    user = await resolve_session(state.db, session_store, token, state.clock)
    request.state.current_user = user
    return user


async def current_user(request: Request) -> CurrentUser:
    user = await optional_user(request)
    if user is None:
        raise Unauthenticated()
    return user
