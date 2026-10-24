import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login

from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_users_admin(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        await u.session.execute(
            text("UPDATE identity.users SET role = 'editor' WHERE role = 'admin'")
        )
    c = client_for(make_app())
    me = await dev_login(c, "boss@corp.com", "admin")
    h = {"X-CSRF-Token": me["csrf_token"]}
    r = await c.post(
        "/api/v1/users", json={"email": "nova@corp.com", "role": "researcher"}, headers=h
    )
    assert r.status_code == 201, r.text
    new = r.json()
    assert (new["invited"], new["display_name"]) == (True, "nova")
    assert (
        await c.post("/api/v1/users", json={"email": "NOVA@corp.com", "role": "editor"}, headers=h)
    ).json()["code"] == "user.email_exists"
    found = (await c.get("/api/v1/users", params={"q": "nova"})).json()["items"]
    assert [x["email"] for x in found] == ["nova@corp.com"]
    last = await c.patch(
        f"/api/v1/users/{me['id']}", json={"role": "editor"}, headers={**h, "If-Match": '"1"'}
    )
    assert (last.status_code, last.json()["code"]) == (409, "user.last_admin")
    up = await c.patch(
        f"/api/v1/users/{new['id']}",
        json={"role": "editor", "display_name": "Nova Editora"},
        headers={**h, "If-Match": f'"{new["version"]}"'},
    )
    assert (up.json()["role"], up.json()["display_name"], up.json()["version"]) == (
        "editor",
        "Nova Editora",
        2,
    )
    assert (
        await c.patch(
            f"/api/v1/users/{new['id']}", json={"active": False}, headers={**h, "If-Match": '"1"'}
        )
    ).status_code == 412

    other = client_for(make_app())
    om = await dev_login(other, "temp@corp.com", "researcher")
    assert (await other.get("/api/v1/me")).status_code == 200
    off = await c.patch(
        f"/api/v1/users/{om['id']}", json={"active": False}, headers={**h, "If-Match": '"1"'}
    )
    assert off.status_code == 200, off.text
    async with db.uow() as u:
        live = (
            await u.session.execute(
                text("SELECT count(*) FROM identity.sessions WHERE user_id = :i"),
                {"i": om["id"]},
            )
        ).scalar()
        audits = (
            await u.session.execute(
                text(
                    "SELECT count(*) FROM audit.audit_log WHERE action IN ('user.created','user.updated')"
                )
            )
        ).scalar()
    assert live == 0
    assert audits >= 3
    assert (await c.get("/api/v1/users", params={"active": "false"})).json()["items"][0][
        "email"
    ] == "temp@corp.com"
