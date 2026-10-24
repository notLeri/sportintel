from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from tests.factories import make_user

from sportintel.main import create_app
from sportintel.modules.identity.application import sessions as app_sessions
from sportintel.modules.identity.application.ports import OidcError
from sportintel.modules.identity.domain.access_policy import OidcIdentity
from sportintel.modules.identity.infrastructure.oidc_fake import FakeOidcProvider
from sportintel.modules.identity.infrastructure.repository import SqlUserRepository
from sportintel.platform.config import Settings
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


@pytest.fixture
async def app_client(db: Database) -> AsyncIterator[tuple[httpx.AsyncClient, FakeOidcProvider]]:
    app_sessions.clear_cache()
    settings = Settings(
        env="local",
        database_url="postgresql+psycopg://u:p@h/db",
        app_base_url="http://testserver",
        oidc_allowed_domains="corp.com",
        bootstrap_admin_email="boss@gmail.com",
    )
    app = create_app(settings)
    app.state.db = db  # SAVEPOINT-база теста
    provider = FakeOidcProvider()
    app.state.oidc = provider
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c, provider
    app_sessions.clear_cache()


def ident(email: str, sub: str | None = None, verified: bool = True) -> OidcIdentity:
    return OidcIdentity(sub or f"sub|{email}", email, verified, email.split("@")[0].title(), None)


async def login(c: httpx.AsyncClient, nxt: str = "/feed") -> httpx.Response:
    r = await c.get("/auth/login", params={"next": nxt})
    assert r.status_code == 302
    assert "oidc_tx" in r.cookies
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    return await c.get("/auth/callback", params={"code": "x@corp.com", "state": state})


async def test_full_login_sets_session_and_redirects_to_next(app_client) -> None:  # type: ignore[no-untyped-def]
    c, provider = app_client
    provider.next_identity = ident("ana@corp.com")
    r = await login(c, "/events/1?x=1")
    assert r.status_code == 302
    assert r.headers["location"] == "/events/1?x=1"
    assert "sid" in r.cookies
    assert provider.calls[0]["code_verifier"]  # PKCE
    set_cookie = r.headers.get_list("set-cookie")
    assert any(h.startswith("sid=") and "HttpOnly" in h for h in set_cookie)
    assert any(h.startswith("oidc_tx=") and "Max-Age=0" in h for h in set_cookie)


async def test_open_redirect_blocked(app_client) -> None:  # type: ignore[no-untyped-def]
    c, provider = app_client
    provider.next_identity = ident("ana@corp.com")
    assert (await login(c, "//evil.com")).headers["location"] == "/"


async def test_repeat_callback_is_state_mismatch(app_client) -> None:  # type: ignore[no-untyped-def]
    c, provider = app_client
    provider.next_identity = ident("ana@corp.com")
    r = await c.get("/auth/login")
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    first = await c.get("/auth/callback", params={"code": "c", "state": state})
    assert first.headers["location"] == "/"
    c.cookies.set("oidc_tx", r.cookies["oidc_tx"], path="/auth")
    again = await c.get("/auth/callback", params={"code": "c", "state": state})
    assert again.headers["location"] == "/login?error=auth.state_mismatch"


async def test_wrong_state_rejected(app_client) -> None:  # type: ignore[no-untyped-def]
    c, _ = app_client
    await c.get("/auth/login")
    r = await c.get("/auth/callback", params={"code": "c", "state": "forged"})
    assert r.headers["location"] == "/login?error=auth.state_mismatch"


@pytest.mark.parametrize(
    ("identity", "error"),
    [
        (ident("x@gmail.com"), "auth.not_allowed"),
        (ident("ana@corp.com", verified=False), "auth.email_not_verified"),
    ],
)
async def test_denied_goes_to_login_with_error(app_client, identity, error) -> None:  # type: ignore[no-untyped-def]
    c, provider = app_client
    provider.next_identity = identity
    r = await login(c)
    assert r.headers["location"] == f"/login?error={error}"
    assert "sid" not in r.cookies


async def test_inactive_user(app_client, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, provider = app_client
    async with db.uow() as u:
        user = await make_user(
            u, email="old@corp.com", oidc_subject="sub|old@corp.com", active=False
        )
    provider.next_identity = ident("old@corp.com")
    assert (await login(c)).headers["location"] == "/login?error=auth.user_inactive"
    async with db.uow() as u:
        assert (await SqlUserRepository(u.session).get(user.id)).active is False  # type: ignore[union-attr]


async def test_idp_error_and_exchange_failure(app_client) -> None:  # type: ignore[no-untyped-def]
    c, provider = app_client
    r = await c.get("/auth/callback", params={"error": "access_denied"})
    assert r.headers["location"] == "/login?error=auth.oidc_failed"
    provider.fail_with = OidcError("timeout")
    assert (await login(c)).headers["location"] == "/login?error=auth.oidc_failed"


async def test_bootstrap_admin_then_email_change_by_subject(app_client, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, provider = app_client
    provider.next_identity = ident("boss@gmail.com", sub="google-42")
    assert (await login(c)).headers["location"] == "/feed"
    async with db.uow() as u:
        repo = SqlUserRepository(u.session)
        boss = await repo.find_by_subject("google-42")
        assert boss is not None
        assert boss.role.value == "admin"
    provider.next_identity = ident("boss.new@gmail.com", sub="google-42")
    c.cookies.clear()
    assert (await login(c)).headers["location"] == "/feed"
    async with db.uow() as u:
        moved = await SqlUserRepository(u.session).find_by_subject("google-42")
    assert moved is not None
    assert (moved.email, moved.id, moved.version) == ("boss.new@gmail.com", boss.id, 2)


async def test_logout_requires_csrf_and_revokes(app_client, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, provider = app_client
    provider.next_identity = ident("ana@corp.com")
    await login(c)
    assert (await c.post("/auth/logout")).status_code == 403
    from sportintel.modules.identity import public as identity
    from sportintel.platform.clock import SystemClock

    token = c.cookies["sid"]
    current = await identity.resolve_session(db, token, SystemClock())
    assert current is not None
    r = await c.post("/auth/logout", headers={"X-CSRF-Token": current.csrf_token})
    assert r.status_code == 200
    assert r.json() == {"logout_url": None}
    app_sessions.clear_cache()
    assert await identity.resolve_session(db, token, SystemClock()) is None
    assert (await c.post("/auth/logout")).status_code == 401
