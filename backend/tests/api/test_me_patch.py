import pytest
from tests.api.conftest import dev_login

pytestmark = pytest.mark.integration


async def test_patch_me_preferences(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    me = await dev_login(c, "prefs@corp.com", "researcher")
    h = {"X-CSRF-Token": me["csrf_token"]}
    r = await c.patch(
        "/api/v1/me",
        json={"locale": "en", "timezone": "Europe/Moscow", "hotkeys_enabled": False},
        headers=h,
    )
    assert r.status_code == 200, r.text
    # Язык интерфейса — общая настройка админа (languages.ui_language), личный выбор не действует.
    assert (r.json()["locale"], r.json()["timezone"], r.json()["hotkeys_enabled"]) == (
        "ru",
        "Europe/Moscow",
        False,
    )
    again = (await c.get("/api/v1/me")).json()
    assert (again["locale"], again["hotkeys_enabled"]) == ("ru", False)
    bad = await c.patch("/api/v1/me", json={"timezone": "Mars/Olympus"}, headers=h)
    assert bad.status_code == 422
    assert bad.json()["errors"][0]["field"].endswith("timezone")
