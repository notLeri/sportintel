import pytest
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.modules.events.domain.values import EventStatus
from sportintel.platform.db import Database
from sportintel.platform.security_headers import headers_for

pytestmark = pytest.mark.integration


async def test_headers_on_api_responses(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    r = await c.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert "content-security-policy" not in r.headers  # CSP — только HTML


def test_csp_modes_and_hsts() -> None:
    prod = dict(headers_for("prod", "enforce", html=True))
    assert prod[b"strict-transport-security"].startswith(b"max-age=31536000")
    assert b"frame-ancestors 'none'" in prod[b"content-security-policy"]
    local = dict(headers_for("local", "report-only", html=True))
    assert b"strict-transport-security" not in local
    assert b"content-security-policy-report-only" in local


async def test_ai_generation_rate_limited(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        ev = await make_event(
            u, [await make_article(u, await make_source(u))], status=EventStatus.SELECTED
        )
    c = client_for(make_app())
    me = await dev_login(c, "rl@corp.com", "researcher")
    h = {"X-CSRF-Token": me["csrf_token"]}
    d = (
        await c.post(
            f"/api/v1/events/{ev.id}/drafts",
            json={},
            headers={
                **h,
                "Idempotency-Key": "0192f6a1-0000-7000-8000-00000000r001".replace("r", "a"),
            },
        )
    ).json()
    codes = [
        (await c.post(f"/api/v1/drafts/{d['id']}:regenerate", json={}, headers=h)).status_code
        for _ in range(10)
    ]
    assert codes[:9] == [200] * 9
    assert codes[9] == 429
    last = await c.post(f"/api/v1/drafts/{d['id']}:regenerate", json={}, headers=h)
    assert int(last.headers["Retry-After"]) >= 1
