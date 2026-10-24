import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_source

from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_summary_failures_and_retry(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s = await make_source(u, name="Fonte Pipeline")
        a1, a2 = (
            await make_article(u, s, title="Falhou fetch"),
            await make_article(u, s, title="Falhou enrich"),
        )
        for a, code in ((a1, "fetch_timeout"), (a2, "enrich_failed")):
            await u.session.execute(
                text(
                    "UPDATE ingestion.articles SET state='failed', failure_code=:c, state_changed_at=now(), discovered_at=now() WHERE id=:i"
                ),
                {"c": code, "i": a.id},
            )
    c = client_for(make_app())
    me = await dev_login(c, "pipe-editor@corp.com", "editor")
    assert (await c.get("/api/v1/pipeline/summary")).status_code == 403
    me = await dev_login(c, "pipe-admin@corp.com", "admin")
    h = {"X-CSRF-Token": me["csrf_token"]}
    s1 = (await c.get("/api/v1/pipeline/summary")).json()
    assert s1["articles_24h"]["failed"] >= 2
    assert {x["code"] for x in s1["failures_by_code"]} >= {"fetch_timeout", "enrich_failed"}
    assert {q["queue"] for q in s1["queues"]} >= {"fetch", "ai", "cluster"}
    fails = (await c.get("/api/v1/pipeline/failures", params={"code": "fetch_timeout"})).json()[
        "articles"
    ]
    assert [(f["title"], f["source_name"]) for f in fails] == [("Falhou fetch", "Fonte Pipeline")]
    assert (
        await c.post(
            "/api/v1/pipeline/failures:retry",
            json={"article_ids": [str(a1.id)], "failure_code": "x"},
            headers=h,
        )
    ).status_code == 422
    r = await c.post(
        "/api/v1/pipeline/failures:retry", json={"failure_code": "enrich_failed"}, headers=h
    )
    assert r.json() == {"retried": 1, "remaining": 0}
    r = await c.post(
        "/api/v1/pipeline/failures:retry", json={"article_ids": [str(a1.id)]}, headers=h
    )
    assert r.json()["retried"] == 1
    async with db.uow() as u:
        states = dict(
            (
                await u.session.execute(
                    text("SELECT id, state FROM ingestion.articles WHERE id IN (:a, :b)"),
                    {"a": a1.id, "b": a2.id},
                )
            ).all()
        )
    assert (states[a1.id], states[a2.id]) == ("discovered", "extracted")
    assert (await c.get("/api/v1/pipeline/failures", params={"kind": "jobs"})).status_code == 200
