import pytest
from sqlalchemy import text

from sportintel.modules.identity import public as identity
from sportintel.modules.identity.api import router as auth_router
from sportintel.platform.clock import SystemClock
from sportintel.platform.config import Settings
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration
PW = "s3cret-password"


@pytest.fixture(autouse=True)
def _fresh_attempts() -> None:
    auth_router.ATTEMPTS.reset_all()


async def _user(db: Database, email: str = "ana@corp.com", role: str = "editor") -> None:
    async with db.uow() as uow:
        await identity.set_password(uow, email, PW, SystemClock(), role=identity.Role(role))


async def test_password_login_opens_session(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    await _user(db)
    c = client_for(make_app(dev_login_enabled=False))
    r = await c.post("/auth/password-login", json={"email": " ANA@corp.com ", "password": PW})
    assert r.status_code == 200, r.text
    assert (r.json()["email"], r.json()["role"]) == ("ana@corp.com", "editor")
    assert (await c.get("/api/v1/me")).status_code == 200


async def test_wrong_password_and_unknown_email_look_the_same(
    make_app, client_for, db: Database
) -> None:  # type: ignore[no-untyped-def]
    await _user(db)
    c = client_for(make_app())
    wrong = await c.post("/auth/password-login", json={"email": "ana@corp.com", "password": "nope"})
    ghost = await c.post("/auth/password-login", json={"email": "no@corp.com", "password": PW})
    assert (wrong.status_code, wrong.json()["code"]) == (401, "auth.bad_credentials")
    assert (ghost.status_code, ghost.json()["code"]) == (401, "auth.bad_credentials")
    async with db.uow() as uow:
        denied = (
            await uow.session.execute(
                text("SELECT count(*) FROM audit.audit_log WHERE action = 'auth.login_denied'")
            )
        ).scalar()
    assert denied == 2


async def test_inactive_user_cannot_log_in(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    await _user(db)
    async with db.uow() as uow:
        await uow.session.execute(text("UPDATE identity.users SET active = false"))
    c = client_for(make_app())
    r = await c.post("/auth/password-login", json={"email": "ana@corp.com", "password": PW})
    assert r.status_code == 401


async def test_rate_limited_after_five_failures(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    await _user(db)
    c = client_for(make_app())
    for _ in range(auth_router.LOGIN_ATTEMPTS):
        await c.post("/auth/password-login", json={"email": "ana@corp.com", "password": "bad"})
    r = await c.post("/auth/password-login", json={"email": "ana@corp.com", "password": PW})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


async def test_initial_admin_created_once(db: Database) -> None:
    async with db.uow() as uow:
        await uow.session.execute(text("UPDATE identity.users SET role = 'editor'"))
    s = Settings(
        env="production",
        database_url="postgresql+psycopg://u:p@h/db",
        app_base_url="https://x",
        bootstrap_admin_email="boss@corp.com",
        initial_admin_password="first-admin-pw",
    )
    assert await identity.ensure_initial_admin(db, s, SystemClock())
    assert not await identity.ensure_initial_admin(db, s, SystemClock())  # admin уже есть
    async with db.uow() as uow:
        role = (
            await uow.session.execute(
                text("SELECT role FROM identity.users WHERE email = 'boss@corp.com'")
            )
        ).scalar()
    assert role == "admin"


async def test_production_without_oidc_disables_idp_login(db: Database, client_for) -> None:  # type: ignore[no-untyped-def]
    from sportintel.main import create_app

    app = create_app(
        Settings(
            env="production", database_url="postgresql+psycopg://u:p@h/db", app_base_url="https://x"
        )
    )
    app.state.db = db
    assert app.state.oidc is None
    r = await client_for(app).get("/auth/login")
    assert r.status_code == 302
    assert r.headers["location"] == "/login?error=auth.oidc_disabled"


async def test_admin_invites_with_password_and_resets_it(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    from tests.api.conftest import dev_login

    admin = client_for(make_app())
    me = await dev_login(admin, "boss@corp.com", "admin")
    h = {"X-CSRF-Token": me["csrf_token"]}
    short = await admin.post(
        "/api/v1/users", json={"email": "n@corp.com", "role": "editor", "password": "x"}, headers=h
    )
    assert short.status_code == 422
    new = (
        await admin.post(
            "/api/v1/users",
            json={"email": "n@corp.com", "role": "editor", "password": PW},
            headers=h,
        )
    ).json()
    assert new["has_password"]
    user = client_for(make_app())
    ok = await user.post("/auth/password-login", json={"email": "n@corp.com", "password": PW})
    assert ok.status_code == 200
    r = await admin.patch(
        f"/api/v1/users/{new['id']}",
        json={"password": "another-password"},
        headers={**h, "If-Match": f'"{new["version"]}"'},
    )
    assert r.status_code == 200, r.text
    assert (await user.get("/api/v1/me")).status_code == 401  # сброс закрыл сессии
    old = await user.post("/auth/password-login", json={"email": "n@corp.com", "password": PW})
    assert old.status_code == 401
