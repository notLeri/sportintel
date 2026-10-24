import uuid

import pytest
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.modules.events.domain.values import EventStatus
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_history_shows_transition_and_draft_save(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        ev = await make_event(
            u, [await make_article(u, await make_source(u), lead="Lead.")], status=EventStatus.NEW
        )
    c = client_for(make_app())
    me = await dev_login(c, "hist-researcher@corp.com", "researcher")
    h = {"X-CSRF-Token": me["csrf_token"]}
    assert (await c.get("/api/v1/audit", params={"event_id": str(ev.id)})).status_code == 403
    me = await dev_login(c, "hist-editor@corp.com", "editor")
    h = {"X-CSRF-Token": me["csrf_token"]}
    r = await c.post(
        f"/api/v1/events/{ev.id}/transitions",
        json={"to": "SELECTED"},
        headers={**h, "If-Match": '"1"'},
    )
    assert r.status_code == 200, r.text
    d = (
        await c.post(
            f"/api/v1/events/{ev.id}/drafts",
            json={},
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
    ).json()
    await c.patch(
        f"/api/v1/drafts/{d['id']}",
        json={"body_tg_html": "Texto"},
        headers={**h, "If-Match": f'"{d["version"]}"'},
    )
    hist = (await c.get("/api/v1/audit", params={"event_id": str(ev.id), "limit": 2})).json()
    assert [i["action"] for i in hist["items"]] == ["draft.saved", "draft.generation_requested"]
    assert hist["items"][0]["actor"]["name"] == "hist-editor"
    more = (
        await c.get("/api/v1/audit", params={"event_id": str(ev.id), "cursor": hist["next_cursor"]})
    ).json()
    assert more["items"][0]["action"] == "event.transitioned"
    assert more["items"][0]["after"]["status"] == "SELECTED"
    assert (await c.get("/api/v1/audit")).status_code == 422
