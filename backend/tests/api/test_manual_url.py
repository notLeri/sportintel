import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login

from sportintel.main import create_app
from sportintel.modules.identity.application import sessions as app_sessions
from sportintel.platform.clock import FrozenClock
from sportintel.platform.config import Settings
from sportintel.platform.db import Database
from sportintel.platform.idempotency import body_hash, purge_expired

pytestmark = pytest.mark.integration_commit
NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


@pytest.fixture
async def client(
    committing_db: Database,
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str], Database]]:
    app_sessions.clear_cache()
    app = create_app(
        Settings(
            env="local",
            database_url="postgresql+psycopg://u:p@h/db",
            app_base_url="http://t",
            dev_login_enabled=True,
        )
    )
    app.state.db = committing_db
    app.state.clock = FrozenClock(NOW)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        me = await dev_login(c, "manual@corp.com", "researcher")
        yield c, {"X-CSRF-Token": me["csrf_token"]}, committing_db
    async with committing_db.uow() as u:
        for sql in (
            "DELETE FROM ingestion.articles",
            "DELETE FROM platform.idempotency_keys",
            "DELETE FROM sources.sources WHERE kind = 'manual'",
            "DELETE FROM identity.sessions",
            "DELETE FROM identity.users",
        ):
            await u.session.execute(text(sql))
    app_sessions.clear_cache()


async def q(db: Database, sql: str) -> object:
    async with db.uow() as u:
        return (await u.session.execute(text(sql))).scalar()


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def test_accepts_and_enqueues_once_per_key(client) -> None:  # type: ignore[no-untyped-def]
    c, h, db = client
    hdr = {**h, **key()}
    body = {"url": "https://www.blogdofutebol.example.org/noticia/x?utm_source=zap"}
    first = await c.post("/api/v1/articles", json=body, headers=hdr)
    assert first.status_code == 202, first.text
    assert first.json()["created"] is True
    again = await c.post("/api/v1/articles", json=body, headers=hdr)
    assert (again.status_code, again.json()) == (202, first.json())
    assert (
        await q(
            db,
            "SELECT count(*) FROM procrastinate.procrastinate_jobs WHERE task_name='ingestion.extract_article'",
        )
        == 1
    )
    assert (
        await q(db, "SELECT kind FROM sources.sources WHERE domain='blogdofutebol.example.org'")
        == "manual"
    )
    assert (
        await q(db, "SELECT manual::text || title FROM ingestion.articles") == "true" + body["url"]
    )


async def test_same_key_other_body_rejected(client) -> None:  # type: ignore[no-untyped-def]
    c, h, _ = client
    hdr = {**h, **key()}
    await c.post("/api/v1/articles", json={"url": "https://a.example.org/1"}, headers=hdr)
    r = await c.post("/api/v1/articles", json={"url": "https://a.example.org/2"}, headers=hdr)
    assert (r.status_code, r.json()["code"]) == (422, "common.idempotency_key_reused")


async def test_existing_url_not_duplicated(client) -> None:  # type: ignore[no-untyped-def]
    c, h, _ = client
    a = await c.post(
        "/api/v1/articles", json={"url": "https://b.example.org/x#top"}, headers={**h, **key()}
    )
    b = await c.post(
        "/api/v1/articles", json={"url": "https://b.example.org/x?fbclid=1"}, headers={**h, **key()}
    )
    assert b.json() == {**a.json(), "created": False}


@pytest.mark.parametrize(
    "url",
    ["ge.globo.com/x", "ftp://x.example.org/a", "https://", "https://x.example.org/" + "a" * 2050],
)
async def test_invalid_url(client, url: str) -> None:  # type: ignore[no-untyped-def]
    c, h, _ = client
    r = await c.post("/api/v1/articles", json={"url": url}, headers={**h, **key()})
    assert r.status_code == 422
    assert r.json()["code"] in {"article.invalid_url", "common.validation_failed"}


async def test_key_required(client) -> None:  # type: ignore[no-untyped-def]
    c, h, _ = client
    r = await c.post("/api/v1/articles", json={"url": "https://c.example.org/1"}, headers=h)
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "Idempotency-Key"


async def test_private_url_accepted_by_api(client) -> None:  # type: ignore[no-untyped-def]
    c, h, _ = client  # SSRF проверит worker (ssrf_blocked), web в сеть не ходит
    assert (
        await c.post(
            "/api/v1/articles", json={"url": "http://10.0.0.5/admin"}, headers={**h, **key()}
        )
    ).status_code == 202


async def test_purge_idempotency(client) -> None:  # type: ignore[no-untyped-def]
    c, h, db = client
    await c.post(
        "/api/v1/articles", json={"url": "https://d.example.org/1"}, headers={**h, **key()}
    )
    assert await purge_expired(db, NOW + timedelta(hours=23)) == 0
    assert await purge_expired(db, NOW + timedelta(hours=25)) == 1


def test_body_hash_ignores_key_order() -> None:
    assert body_hash("POST", "/p", {"a": 1, "b": [1, 2]}) == body_hash(
        "POST", "/p", {"b": [1, 2], "a": 1}
    )
    assert body_hash("POST", "/p", {"a": 1}) != body_hash("POST", "/q", {"a": 1})
