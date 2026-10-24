from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from sportintel.main import create_app
from sportintel.modules.identity.application import sessions as app_sessions
from sportintel.platform.config import Settings
from sportintel.platform.db import Database

AppFactory = Callable[..., FastAPI]


@pytest.fixture
def make_app(db: Database) -> AppFactory:
    """create_app на SAVEPOINT-базе теста; настройки можно переопределить."""

    def factory(**overrides: Any) -> FastAPI:
        app_sessions.clear_cache()
        base: dict[str, Any] = {
            "env": "local",
            "database_url": "postgresql+psycopg://u:p@h/db",
            "app_base_url": "http://testserver",
            "dev_login_enabled": True,
        }
        app = create_app(Settings(**{**base, **overrides}))
        app.state.db = db
        return app

    return factory


@pytest.fixture
async def client_for() -> AsyncIterator[Callable[[FastAPI], httpx.AsyncClient]]:
    clients: list[httpx.AsyncClient] = []

    def make(app: FastAPI) -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()
    app_sessions.clear_cache()


async def dev_login(
    c: httpx.AsyncClient, email: str = "ana@corp.com", role: str = "editor"
) -> dict[str, Any]:
    r = await c.post("/auth/dev-login", json={"email": email, "role": role})
    assert r.status_code == 200, r.text
    return r.json()
