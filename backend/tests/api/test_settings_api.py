import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login

from sportintel.platform import settings_store
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_settings_list_put_validation_and_audit(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    settings_store.clear_cache()
    c = client_for(make_app())
    me = await dev_login(c, "settings-editor@corp.com", "editor")
    assert (await c.get("/api/v1/settings")).status_code == 403
    me = await dev_login(c, "settings-admin@corp.com", "admin")
    h = {"X-CSRF-Token": me["csrf_token"]}
    items = {i["key"]: i for i in (await c.get("/api/v1/settings")).json()["items"]}
    assert {"clustering", "enrich_rules", "ai_routing", "drafts"} <= set(items)
    assert items["clustering"]["value"]["t_high"] == 0.58
    assert "properties" in items["clustering"]["schema"]
    assert items["enrich_rules"]["default"][
        "relevance_rules"
    ]  # seed правил через DEFAULT_OVERRIDES
    bad = await c.put(
        "/api/v1/settings/clustering",
        json={"value": {**items["clustering"]["value"], "t_low": 0.9}},
        headers=h,
    )
    assert (bad.status_code, bad.json()["code"]) == (422, "settings.invalid_value")
    ok = await c.put(
        "/api/v1/settings/clustering",
        json={"value": {**items["clustering"]["value"], "t_high": 0.6}},
        headers=h,
    )
    assert ok.status_code == 200, ok.text
    assert (ok.json()["value"]["t_high"], ok.json()["updated_by"]) == (0.6, me["id"])
    assert (await c.get("/api/v1/settings/nope")).status_code == 404
    async with db.uow() as u:
        a = (
            await u.session.execute(
                text(
                    "SELECT before, after FROM audit.audit_log WHERE action='settings.updated' AND target_id='clustering'"
                )
            )
        ).one()
    assert a.after["t_high"] == 0.6
    async with db.uow() as u:
        await u.session.execute(text("DELETE FROM platform.app_settings WHERE key='clustering'"))
    settings_store.clear_cache()
