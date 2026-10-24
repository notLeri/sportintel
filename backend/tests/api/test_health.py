from collections.abc import AsyncIterator

import httpx
import pytest

from sportintel.main import create_app
from sportintel.platform.config import Settings


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def test_healthz(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "dev"}
    assert r.headers["x-request-id"]


async def test_request_id_passthrough(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz", headers={"X-Request-ID": "abc-12345678"})
    assert r.headers["x-request-id"] == "abc-12345678"


@pytest.mark.parametrize("bad", ["short", "has space here!", "x" * 65, "<script>alert</script>"])
async def test_request_id_garbage_replaced(client: httpx.AsyncClient, bad: str) -> None:
    r = await client.get("/healthz", headers={"X-Request-ID": bad})
    assert r.headers["x-request-id"] != bad
    assert len(r.headers["x-request-id"]) == 36


def test_create_app_twice_does_not_duplicate_log_handlers(settings: Settings) -> None:
    import logging

    create_app(settings)
    create_app(settings)
    assert len(logging.getLogger().handlers) == 1


@pytest.mark.parametrize(("env", "status"), [("staging", 200), ("production", 404)])
async def test_openapi_docs_only_outside_production(env: str, status: int) -> None:
    extra = {"oidc_issuer": "https://i", "oidc_client_id": "c", "oidc_client_secret": "s"}
    s = Settings(
        env=env, database_url="postgresql+psycopg://u:p@h/db", app_base_url="http://t", **extra
    )
    transport = httpx.ASGITransport(app=create_app(s))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.get("/api/v1/openapi.json")).status_code == status
