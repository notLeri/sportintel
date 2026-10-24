import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_source

from sportintel.composition import system_status
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_me_has_system_status(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    system_status.clear_cache()
    async with db.uow() as u:
        s = await make_source(u)
        await u.session.execute(
            text("UPDATE sources.sources SET health = 'down' WHERE id = :i"), {"i": s.id}
        )
        await u.session.execute(
            text(
                "INSERT INTO platform.alert_state (alert_key, firing) VALUES ('ingest_lag', true) ON CONFLICT (alert_key) DO UPDATE SET firing = true"
            )
        )
    c = client_for(make_app())
    await dev_login(c, "status@corp.com", "researcher")
    st = (await c.get("/api/v1/me")).json()["system_status"]
    assert st["ai"] == {
        "mode": "rules",
        "llm": {"configured": False, "available": False, "model": None},
    }
    assert st["sources_down"] >= 1
    assert st["pipeline_delayed"] is True
    async with db.uow() as u:
        await u.session.execute(text("DELETE FROM platform.alert_state"))
    system_status.clear_cache()
