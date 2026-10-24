from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from sportintel.main import create_app
from sportintel.platform.config import Settings


@pytest.fixture
async def client(tmp_path: Path, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        '<!doctype html><meta name="app-env" content="%APP_ENV%"><div id=root></div>'
    )
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "robots.txt").write_text("User-agent: *")
    (tmp_path.parent / "secret.txt").write_text("nope")
    app = create_app(settings.model_copy(update={"static_dir": str(tmp_path)}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_assets_are_immutable(client: httpx.AsyncClient) -> None:
    r = await client.get("/assets/app-abc123.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.parametrize(
    "path", ["/", "/events/0192f6a1-0000-7000-8000-000000000001", "/feed?tab=channel"]
)
async def test_spa_routes_get_index_no_cache(client: httpx.AsyncClient, path: str) -> None:
    r = await client.get(path)
    assert r.status_code == 200
    assert "id=root" in r.text
    assert r.headers["cache-control"] == "no-cache"


async def test_root_files_served(client: httpx.AsyncClient) -> None:
    assert (await client.get("/robots.txt")).text == "User-agent: *"


@pytest.mark.parametrize("path", ["/api/v1/nope", "/auth/nope"])
async def test_api_prefixes_not_spa(client: httpx.AsyncClient, path: str) -> None:
    r = await client.get(path)
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"


async def test_no_path_traversal(client: httpx.AsyncClient) -> None:
    r = await client.get("/..%2Fsecret.txt")
    assert "nope" not in r.text


async def test_health_still_works(client: httpx.AsyncClient) -> None:
    assert (await client.get("/healthz")).json()["status"] == "ok"


async def test_no_static_dir_means_no_spa(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"static_dir": "/nonexistent"}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/")).status_code == 404


async def test_env_injected_into_index(client: httpx.AsyncClient) -> None:
    assert 'content="ci"' in (await client.get("/")).text
