import pytest
from tests.api.conftest import dev_login

pytestmark = pytest.mark.integration


async def test_me_requires_session(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    r = await client_for(make_app()).get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["code"] == "common.unauthenticated"


async def test_me_shape(make_app, client_for, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FLAG_BROWSER_NOTIFICATIONS", "true")
    c = client_for(make_app())
    await dev_login(c, role="researcher")
    me = (await c.get("/api/v1/me")).json()
    assert me["csrf_token"]
    assert me["locale"] == "ru"
    assert me["timezone"] == "America/Sao_Paulo"
    assert "events.override_assessment" not in me["permissions"]
    assert {"self.read", "events.read", "drafts.write"} <= set(me["permissions"])
    assert me["flags"] == {
        "BROWSER_NOTIFICATIONS": True,
        "REQUIRE_SECOND_REVIEWER": False,
        "TELEGRAM_PUBLISH": False,
    }
    assert "REJECTED" in {o["to"] for o in me["allowed_transitions"]["NEW"]}  # BE-T3.2
    assert me["system_status"]["ai"]["mode"] == "rules"  # BE-T4.14


@pytest.mark.parametrize(
    ("role", "has", "lacks"),
    [
        ("editor", "audit.read", "users.manage"),
        ("admin", "users.manage", None),
    ],
)
async def test_permissions_by_role(make_app, client_for, role, has, lacks) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    perms = set((await dev_login(c, f"{role}@x.com", role))["permissions"])
    assert has in perms
    if lacks:
        assert lacks not in perms
