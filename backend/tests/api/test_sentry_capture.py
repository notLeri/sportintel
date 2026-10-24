import httpx
import sentry_sdk
from tests.conftest import CaptureTransport

from sportintel.main import create_app
from sportintel.platform import errors
from sportintel.platform.config import Settings


async def test_unhandled_web_error_reaches_sentry_scrubbed(
    settings: Settings, captured: CaptureTransport
) -> None:
    s = Settings(
        env="ci",
        database_url=settings.database_url,
        app_base_url=settings.app_base_url,
        sentry_dsn="https://k@o0.ingest.sentry.io/1",
        version="abc123",
    )
    app = create_app(s)

    @app.get("/_boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    @app.get("/_notfound")
    async def nf() -> None:
        raise errors.NotFound()

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        await c.get("/_notfound")
        await c.get("/_boom", headers={"Cookie": "sid=s", "X-Request-ID": "req-sentry-1"})
    sentry_sdk.flush()

    errors_seen = [e for e in captured.events if e.get("exception")]
    assert len(errors_seen) >= 1
    ev = errors_seen[0]
    assert ev["environment"] == "ci"
    assert ev["release"] == "abc123"
    assert ev["exception"]["values"][-1]["value"] == "kaboom"
    assert "cookie" not in {k.lower() for k in ev.get("request", {}).get("headers", {})}
    assert ev["tags"]["request_id"] == "req-sentry-1"
    types = [e.get("exception", {}).get("values", [{}])[-1].get("type") for e in captured.events]
    assert types == ["RuntimeError"]  # одно событие на 500; 4xx DomainError не отправлен
