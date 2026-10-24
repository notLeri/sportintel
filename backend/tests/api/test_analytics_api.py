import uuid

import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.modules.events.domain.values import AssessmentOrigin, Relevance, RelevanceAssessment
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_summary_from_real_actions(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        await u.session.execute(text("DELETE FROM audit.audit_log"))
        s = await make_source(u, name="Fonte Líder")
        hot = await make_event(
            u,
            [await make_article(u, s)],
            relevance=RelevanceAssessment(Relevance.HIGH, "r", AssessmentOrigin.RULE),
        )
        cold = await make_event(u, [await make_article(u, s)])
    c = client_for(make_app())
    me = await dev_login(c, "ana-analytics@corp.com", "editor")
    h = {"X-CSRF-Token": me["csrf_token"]}
    assert (
        await c.post(
            f"/api/v1/events/{hot.id}/transitions",
            json={"to": "SELECTED"},
            headers={**h, "If-Match": '"1"'},
        )
    ).status_code == 200
    r = await c.post(
        f"/api/v1/events/{cold.id}/transitions",
        json={"to": "REJECTED", "reason": "IRRELEVANT"},
        headers={**h, "If-Match": '"1"'},
    )
    assert r.status_code == 200
    assert (
        await c.post("/api/v1/analytics/heartbeat", json={"event_id": str(hot.id)}, headers=h)
    ).status_code == 204
    out = (await c.get("/api/v1/analytics/summary")).json()
    t = out["totals"]
    assert t["useful_stories"] == 1
    assert t["active_hours"] > 0
    assert t["uspH"] > 0
    assert out["rows"][0]["label"] == "ana-analytics"
    assert {"status": "SELECTED", "count": 1} in out["funnel"]
    assert out["reject_reasons"] == [{"reason": "IRRELEVANT", "count": 1}]
    assert out["first_source_leaders"][0]["name"] == "Fonte Líder"
    days = (await c.get("/api/v1/analytics/summary", params={"group_by": "day"})).json()
    assert days["rows"][0]["useful_stories"] == 1
    assert (
        await c.get("/api/v1/analytics/summary", params={"from": "2026-01-01", "to": "2026-10-09"})
    ).status_code == 422
    rs = client_for(make_app())
    await dev_login(rs, f"res-{uuid.uuid4().hex[:4]}@corp.com", "researcher")
    assert (await rs.get("/api/v1/analytics/summary")).status_code == 403
