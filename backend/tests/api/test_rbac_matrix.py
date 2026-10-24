"""Генерируемая матрица RBAC по всем маршрутам приложения (BE-T0.17 §18)."""

import re
import uuid

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from tests.api.conftest import dev_login

from sportintel.modules.identity import public as identity
from sportintel.modules.identity.domain.values import Role

pytestmark = pytest.mark.integration
PLACEHOLDER = str(uuid.UUID(int=1))


def api_routes(app: FastAPI) -> list[tuple[APIRoute, str, str]]:
    """(маршрут, полный путь с префиксами, метод) — FastAPI ≥ 0.142 вкладывает роутеры."""
    out = []
    for ctx in iter_route_contexts(app.routes):
        route = ctx.original_route
        if isinstance(route, APIRoute) and ctx.path:
            for method in sorted((ctx.methods or set()) - {"HEAD", "OPTIONS"}):
                out.append((route, ctx.path, method))
    return out


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", PLACEHOLDER, path)


async def test_every_route_declares_permission(make_app) -> None:  # type: ignore[no-untyped-def]
    routes = api_routes(make_app())
    assert {p for _, p, _ in routes} >= {"/healthz", "/api/v1/me", "/auth/login"}
    missing = [p for r, p, _ in routes if identity.declared_permission(r) is None]
    assert missing == []


async def test_protected_routes_need_session(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    c = client_for(app)
    for route, path, method in api_routes(app):
        if identity.declared_permission(route) == "public":
            continue
        r = await c.request(method, concrete(path), json={})
        assert r.status_code == 401, (method, path, r.status_code)


@pytest.mark.parametrize("role", [r.value for r in Role])
async def test_role_matrix(make_app, client_for, role: str) -> None:  # type: ignore[no-untyped-def]
    app = make_app()
    c = client_for(app)
    me = await dev_login(c, f"{role}@rbac.test", role)
    granted = set(me["permissions"])
    headers = {"X-CSRF-Token": me["csrf_token"]}  # иначе 403 придёт от CSRF, а не от прав (§22)
    checked = 0
    for route, path, method in api_routes(app):
        perm = identity.declared_permission(route)
        if perm == "public":
            continue
        r = await c.request(method, concrete(path), json={}, headers=headers)
        if perm in granted:
            assert r.status_code not in (401, 403), (role, method, path, r.text)
        else:
            assert r.status_code == 403, (role, method, path, r.status_code)
            assert r.json()["code"] == "common.forbidden"
        checked += 1
    assert checked > 0
