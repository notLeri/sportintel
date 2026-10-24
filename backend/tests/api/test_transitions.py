import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.modules.events.domain.values import EventStatus
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def setup(
    make_app, client_for, db: Database, role: str, status: EventStatus = EventStatus.NEW, **kw
):  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s = await make_source(u)
        ev = await make_event(u, [await make_article(u, s)], status=status, **kw)
    c = client_for(make_app())
    me = await dev_login(c, f"tr-{role}@corp.com", role)
    return c, {"X-CSRF-Token": me["csrf_token"]}, ev, me


async def go(c, h, ev_id, version, **body):  # type: ignore[no-untyped-def]
    return await c.post(
        f"/api/v1/events/{ev_id}/transitions", json=body, headers={**h, "If-Match": f'"{version}"'}
    )


async def test_researcher_flow_and_forbidden(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h, ev, me = await setup(make_app, client_for, db, "researcher")
    assert me["allowed_transitions"]["NEW"][0]["to"] in {"REVIEWING", "SELECTED"}
    assert "READY" not in me["allowed_transitions"]
    r = await go(c, h, ev.id, 1, to="SELECTED")
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.headers["ETag"]) == ("SELECTED", '"2"')
    assert (await go(c, h, ev.id, 1, to="DRAFT")).status_code == 412
    assert (await go(c, h, ev.id, 2, to="SELECTED")).json()["code"] == "event.invalid_transition"
    assert (await go(c, h, ev.id, 2, to="DRAFT")).status_code == 200
    r = await go(c, h, ev.id, 3, to="READY")
    assert (r.status_code, r.json()["code"]) == (403, "event.transition_forbidden")
    async with db.uow() as u:
        n = (
            await u.session.execute(
                text(
                    "SELECT count(*) FROM audit.audit_log WHERE target_id=:i AND action='event.transitioned'"
                ),
                {"i": str(ev.id)},
            )
        ).scalar()
    assert n == 2


async def test_editor_ready_needs_draft_and_reject_rules(
    make_app, client_for, db: Database
) -> None:  # type: ignore[no-untyped-def]
    c, h, ev, me = await setup(make_app, client_for, db, "editor", EventStatus.DRAFT)
    assert {"to": "PUBLISHED", "min_role": "editor"} in me["allowed_transitions"]["READY"]
    r = await go(c, h, ev.id, 1, to="READY")
    assert (r.status_code, r.json()["code"]) == (409, "event.invalid_transition")
    r = await go(c, h, ev.id, 1, to="REJECTED")
    assert (r.status_code, r.json()["code"]) == (422, "event.reason_required")
    r = await go(c, h, ev.id, 1, to="REJECTED", reason="OTHER")
    assert (r.status_code, r.json()["code"]) == (422, "event.comment_required")
    r = await go(c, h, ev.id, 1, to="SELECTED", reason="DUPLICATE")
    assert r.status_code == 422
    r = await go(c, h, ev.id, 1, to="REJECTED", reason="OTHER", comment="fora do escopo")
    assert (r.status_code, r.json()["status"]) == (200, "REJECTED")
    assert (await go(c, h, ev.id, 2, to="NEW")).json()["status"] == "NEW"


async def test_ready_with_draft_ready(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h, ev, _ = await setup(
        make_app, client_for, db, "editor", EventStatus.DRAFT, draft_state="ready"
    )
    assert (await go(c, h, ev.id, 1, to="READY")).json()["status"] == "READY"
