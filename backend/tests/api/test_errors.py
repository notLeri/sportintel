from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from fastapi import FastAPI, Query

from sportintel.main import create_app
from sportintel.platform import errors as e
from sportintel.platform.config import Settings

CASES: list[tuple[e.DomainError, int, str]] = [
    (
        e.ValidationFailed(details=[e.FieldError("reason", "required", "Reason is required")]),
        422,
        "common.validation_failed",
    ),
    (e.NotFound(), 404, "common.not_found"),
    (e.Unauthenticated(), 401, "common.unauthenticated"),
    (e.Forbidden(), 403, "common.forbidden"),
    (e.CsrfFailed(), 403, "common.csrf_failed"),
    (e.PreconditionRequired(), 428, "common.precondition_required"),
    (e.ConcurrencyConflict(current={"id": "x", "version": 3}), 412, "common.version_conflict"),
    (e.IdempotencyKeyReused(), 422, "common.idempotency_key_reused"),
    (e.PayloadTooLarge(), 413, "common.payload_too_large"),
    (e.RateLimited(retry_after_s=30), 429, "common.rate_limited"),
    (e.BudgetExhausted(retry_after_s=3600), 429, "ai.budget_exhausted"),
    (e.AiUnavailable(), 503, "ai.unavailable"),
    (e.Conflict(code="event.invalid_transition"), 409, "event.invalid_transition"),
]


def _raiser(err: e.DomainError) -> Callable[[], Awaitable[None]]:
    async def raise_it() -> None:
        raise err

    return raise_it


def _app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    for i, (err, _, _) in enumerate(CASES):
        app.add_api_route(f"/_test/domain/{i}", _raiser(err))

    @app.get("/_test/limit")
    async def limited(limit: int = Query(ge=1, le=100)) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("secret SELECT * FROM users /etc/passwd")

    return app


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_app(settings), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def assert_problem(r: httpx.Response, status: int, code: str) -> dict:
    assert r.status_code == status
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["code"] == code
    assert body["status"] == status
    assert body["type"] == f"https://sportintel/errors/{code}"
    assert body["request_id"] == r.headers["x-request-id"]
    assert set(body) >= {"title", "detail", "errors", "current"}
    return body


@pytest.mark.parametrize(("i", "status", "code"), [(i, s, c) for i, (_, s, c) in enumerate(CASES)])
async def test_domain_errors(client: httpx.AsyncClient, i: int, status: int, code: str) -> None:
    assert_problem(await client.get(f"/_test/domain/{i}"), status, code)


async def test_field_errors_and_current(client: httpx.AsyncClient) -> None:
    body = (await client.get("/_test/domain/0")).json()
    assert body["errors"] == [
        {"field": "reason", "code": "required", "message": "Reason is required"}
    ]
    assert body["current"] is None
    assert (await client.get("/_test/domain/6")).json()["current"] == {"id": "x", "version": 3}


async def test_retry_after_header(client: httpx.AsyncClient) -> None:
    assert (await client.get("/_test/domain/9")).headers["retry-after"] == "30"
    assert (await client.get("/_test/domain/10")).headers["retry-after"] == "3600"


@pytest.mark.parametrize("query", ["", "?limit=0", "?limit=abc"])
async def test_pydantic_validation(client: httpx.AsyncClient, query: str) -> None:
    body = assert_problem(await client.get(f"/_test/limit{query}"), 422, "common.validation_failed")
    assert body["errors"][0]["field"] == "limit"
    assert body["errors"][0]["code"]


async def test_unknown_route_404(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/nope"), 404, "common.not_found")


async def test_method_not_allowed(client: httpx.AsyncClient) -> None:
    r = await client.post("/healthz")
    assert_problem(r, 405, "common.validation_failed")
    assert r.headers["allow"] == "GET"


async def test_unhandled_exception_hides_text(client: httpx.AsyncClient) -> None:
    r = await client.get("/_test/boom", headers={"X-Request-ID": "req-boom-0001"})
    body = assert_problem(r, 500, "common.internal")
    assert body["detail"] == "Internal error"
    assert body["request_id"] == "req-boom-0001"
    for leak in ("secret", "SELECT", "passwd", "RuntimeError", "Traceback"):
        assert leak not in r.text
