import asyncio

import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.modules.events.application.merge_move import merge_events
from sportintel.modules.events.domain.values import EventStatus
from sportintel.modules.events.jobs import repo_for
from sportintel.platform.clock import SystemClock
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def client(make_app, client_for):  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    me = await dev_login(c, "merge@corp.com", "researcher")
    return c, {"X-CSRF-Token": me["csrf_token"]}


async def test_merge_and_move(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s = await make_source(u)
        a1, a2, a3 = (
            await make_article(u, s, title="A"),
            await make_article(u, s, title="B"),
            await make_article(u, s, title="C"),
        )
        target = await make_event(u, [a1])
        source = await make_event(u, [a2, a3])
        ready = await make_event(u, [await make_article(u, s)], status=EventStatus.READY)
    c, h = await client(make_app, client_for)
    r = await c.post(
        f"/api/v1/events/{target.id}/merge",
        json={"other_event_id": str(source.id)},
        headers={**h, "If-Match": '"1"'},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["article_count"] == 3
    assert {a["attach_method"] for a in body["articles"]} == {"new", "manual"}
    src = (await c.get(f"/api/v1/events/{source.id}")).json()
    assert (src["status"], src["rejection_reason"], src["article_count"]) == (
        "REJECTED",
        "DUPLICATE",
        0,
    )
    assert (
        await c.post(
            f"/api/v1/events/{target.id}/merge",
            json={"other_event_id": str(target.id)},
            headers={**h, "If-Match": f'"{body["version"]}"'},
        )
    ).json()["code"] == "event.same_event"
    assert (
        await c.post(
            f"/api/v1/events/{target.id}/merge",
            json={"other_event_id": str(ready.id)},
            headers={**h, "If-Match": f'"{body["version"]}"'},
        )
    ).status_code == 409

    mv = await c.post(
        f"/api/v1/events/{target.id}/articles/{a3.id}/move",
        json={"target_event_id": None},
        headers={**h, "If-Match": f'"{body["version"]}"'},
    )
    assert mv.status_code == 200, mv.text
    new_id = mv.json()["target_event_id"]
    assert mv.json()["source"]["article_count"] == 2
    new = (await c.get(f"/api/v1/events/{new_id}")).json()
    assert (new["title"], new["articles"][0]["attach_method"]) == ("C", "manual")
    missing = await c.post(
        f"/api/v1/events/{target.id}/articles/{a3.id}/move",
        json={"target_event_id": None},
        headers={**h, "If-Match": f'"{mv.json()["source"]["version"]}"'},
    )
    assert missing.json()["code"] == "event.article_not_in_event"
    async with db.uow() as u:
        locked = (
            await u.session.execute(
                text("SELECT cluster_locked FROM events.event_articles WHERE article_id=:a"),
                {"a": a2.id},
            )
        ).scalar()
        audits = (
            await u.session.execute(
                text(
                    "SELECT count(*) FROM audit.audit_log WHERE action IN ('event.merged','event.article_moved')"
                )
            )
        ).scalar()
    assert locked is True
    assert audits == 3


@pytest.mark.integration_commit
async def test_crossed_merges_do_not_deadlock(committing_db: Database) -> None:
    db = committing_db
    async with db.uow() as u:
        s = await make_source(u, domain="deadlock.example.com")
        x = await make_event(u, [await make_article(u, s)])
        y = await make_event(u, [await make_article(u, s)])
    import uuid

    actor = uuid.uuid4()

    async def run(t, o):  # type: ignore[no-untyped-def]
        try:
            async with db.uow() as u:
                await merge_events(u, repo_for, t, o, actor, "researcher", 1, SystemClock())
            return "ok"
        except Exception as e:  # второй получит конфликт версии или недопустимый переход
            return type(e).__name__

    results = await asyncio.wait_for(asyncio.gather(run(x.id, y.id), run(y.id, x.id)), timeout=20)
    assert "ok" in results
    async with db.uow() as u:
        for sql in (
            "DELETE FROM events.event_relations",
            "DELETE FROM events.event_articles",
            "DELETE FROM events.events",
            "DELETE FROM ingestion.articles",
            "DELETE FROM sources.sources WHERE domain = 'deadlock.example.com'",
        ):
            await u.session.execute(text(sql))
