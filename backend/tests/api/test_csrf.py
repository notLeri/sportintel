from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from tests.api.conftest import dev_login

from sportintel.modules.identity import public as identity

pytestmark = pytest.mark.integration


def with_mutation(app: FastAPI) -> FastAPI:
    @app.post("/api/v1/_test/mutate")
    async def mutate(
        user: Annotated[identity.CurrentUser, Depends(identity.current_user)],
    ) -> dict[str, str]:
        return {"ok": user.email}

    @app.get("/api/v1/_test/read")
    async def read(
        user: Annotated[identity.CurrentUser, Depends(identity.current_user)],
    ) -> dict[str, str]:
        return {"ok": user.email}

    return app


async def test_post_without_token_403(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(with_mutation(make_app()))
    await dev_login(c)
    r = await c.post("/api/v1/_test/mutate")
    assert r.status_code == 403
    assert r.json()["code"] == "common.csrf_failed"
    assert r.json()["request_id"] == r.headers["x-request-id"]


async def test_post_with_wrong_token_403(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(with_mutation(make_app()))
    await dev_login(c)
    assert (
        await c.post("/api/v1/_test/mutate", headers={"X-CSRF-Token": "nope"})
    ).status_code == 403


async def test_post_with_right_token_passes(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(with_mutation(make_app()))
    me = await dev_login(c)
    r = await c.post("/api/v1/_test/mutate", headers={"X-CSRF-Token": me["csrf_token"]})
    assert r.status_code == 200


async def test_get_needs_no_token(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(with_mutation(make_app()))
    await dev_login(c)
    assert (await c.get("/api/v1/_test/read")).status_code == 200


async def test_no_cookie_but_token_is_401_not_403(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(with_mutation(make_app()))
    r = await c.post("/api/v1/_test/mutate", headers={"X-CSRF-Token": "anything"})
    assert r.status_code == 401


async def test_logout_needs_csrf_then_clears_session(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    me = await dev_login(c)
    assert (await c.post("/auth/logout")).status_code == 403
    assert (
        await c.post("/auth/logout", headers={"X-CSRF-Token": me["csrf_token"]})
    ).status_code == 200
    assert (await c.get("/api/v1/me")).status_code == 401
