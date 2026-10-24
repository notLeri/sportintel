import pytest
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_override_survives_refresh_and_clears(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        ev = await make_event(u, [await make_article(u, await make_source(u))])
    c = client_for(make_app())
    me = await dev_login(c, "ov-researcher@corp.com", "researcher")
    h = {"X-CSRF-Token": me["csrf_token"]}
    url = f"/api/v1/events/{ev.id}/relevance"
    assert (
        await c.put(
            url, json={"level": "HIGH", "reason": "decisão"}, headers={**h, "If-Match": '"1"'}
        )
    ).status_code == 403
    me = await dev_login(c, "ov-editor@corp.com", "editor")
    h = {"X-CSRF-Token": me["csrf_token"]}
    bad = await c.put(url, json={"level": "HIGH", "reason": "x"}, headers={**h, "If-Match": '"1"'})
    assert (bad.status_code, bad.json()["code"]) == (422, "event.override_reason_required")
    r = await c.put(
        url, json={"level": "HIGH", "reason": "decisão editorial"}, headers={**h, "If-Match": '"1"'}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["relevance"], r.json()["relevance_origin"], r.json()["relevance_reason"]) == (
        "HIGH",
        "human",
        "decisão editorial",
    )
    rel = await c.put(
        f"/api/v1/events/{ev.id}/reliability",
        json={"level": "LOW", "reason": "fonte duvidosa"},
        headers={**h, "If-Match": f'"{r.json()["version"]}"'},
    )
    assert rel.json()["reliability_factors"][0]["code"] == "human_override"
    cleared = await c.put(
        url, json={"level": None}, headers={**h, "If-Match": f'"{rel.json()["version"]}"'}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["relevance_origin"] != "human"
    assert cleared.json()["reliability"] == "LOW"  # второй override остался
