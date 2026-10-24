from datetime import UTC, datetime, timedelta

import pytest
from tests.api.conftest import dev_login
from tests.factories import make_source

from sportintel.modules.sources import public as sources_public
from sportintel.platform.db import Database
from sportintel.platform.ids import new_id

pytestmark = pytest.mark.integration
T0 = datetime(2026, 10, 7, 12, tzinfo=UTC)


async def test_runs_paginated_newest_first(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        source = await make_source(u, domain="runs.example.com")
        for i in range(5):
            await sources_public.record_fetch_run(
                u,
                sources_public.FetchRunRecord(
                    id=new_id(),
                    source_id=source.id,
                    feed_url="https://runs.example.com/feed",
                    started_at=T0 + timedelta(minutes=i),
                    finished_at=T0 + timedelta(minutes=i, seconds=2),
                    status="ok" if i % 2 == 0 else "error",
                    items_seen=i,
                    items_new=0,
                    error_code=None if i % 2 == 0 else "fetch_timeout",
                ),
            )
    c = client_for(make_app())
    await dev_login(c, "admin@corp.com", "admin")
    first = (await c.get(f"/api/v1/sources/{source.id}/runs", params={"limit": 2})).json()
    assert [r["items_seen"] for r in first["items"]] == [4, 3]
    assert first["items"][1]["error_code"] == "fetch_timeout"
    second = (
        await c.get(
            f"/api/v1/sources/{source.id}/runs", params={"limit": 2, "cursor": first["next_cursor"]}
        )
    ).json()
    third = (
        await c.get(
            f"/api/v1/sources/{source.id}/runs",
            params={"limit": 2, "cursor": second["next_cursor"]},
        )
    ).json()
    assert [r["items_seen"] for r in second["items"] + third["items"]] == [2, 1, 0]
    assert third["next_cursor"] is None
    bad = await c.get(f"/api/v1/sources/{source.id}/runs", params={"cursor": "garbage!"})
    assert (bad.status_code, bad.json()["errors"][0]["field"]) == (422, "cursor")
