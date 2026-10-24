import pytest
from pydantic import SecretStr
from tests.api.conftest import dev_login

from sportintel.platform.config import Settings

pytestmark = pytest.mark.integration


async def test_dev_login_local_creates_user_and_session(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    me = await dev_login(c, "dev@x.com", "admin")
    assert (me["email"], me["role"]) == ("dev@x.com", "admin")
    assert "sid" in c.cookies
    assert (await c.get("/api/v1/me")).json()["id"] == me["id"]
    again = await dev_login(c, "dev@x.com", "researcher")  # тот же пользователь, новая роль
    assert (again["id"], again["role"]) == (me["id"], "researcher")


async def test_dev_login_validates_body(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    r = await c.post("/auth/dev-login", json={"email": "not-an-email", "role": "god"})
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} == {"email", "role"}


async def test_dev_login_absent_when_disabled(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app(dev_login_enabled=False))
    assert (
        await c.post("/auth/dev-login", json={"email": "a@b.co", "role": "admin"})
    ).status_code == 404


async def test_dev_login_absent_in_staging_even_if_forced(db, client_for) -> None:  # type: ignore[no-untyped-def]
    from sportintel.main import create_app

    forced = Settings.model_construct(  # мимо валидатора — имитация ошибки конфигурации
        **{
            **Settings(
                env="local", database_url="postgresql+psycopg://u:p@h/db", app_base_url="http://t"
            ).model_dump(),
            "env": "staging",
            "dev_login_enabled": True,
            "oidc_issuer": "https://i",
            "oidc_client_id": "c",
            "oidc_client_secret": SecretStr("s"),
        }
    )
    app = create_app(forced)
    app.state.db = db
    r = await client_for(app).post("/auth/dev-login", json={"email": "a@b.co", "role": "admin"})
    assert r.status_code == 404
