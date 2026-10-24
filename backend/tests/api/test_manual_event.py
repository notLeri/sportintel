import uuid

import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_entity, make_event, make_source

from sportintel.modules.events.application.cluster_article import cluster_article
from sportintel.modules.events.jobs import find_candidates, repo_for
from sportintel.platform.clock import SystemClock
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def client(make_app, client_for):  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    me = await dev_login(c, "manual-ev@corp.com", "researcher")
    return c, {"X-CSRF-Token": me["csrf_token"], "Idempotency-Key": str(uuid.uuid4())}


async def test_create_manual_event_with_urls_and_attach(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        team = await make_entity(u, "Time Manual")
        s = await make_source(u, domain="taken.example.com")
        taken = await make_article(u, s, url="https://taken.example.com/noticia/1")
        other = await make_event(u, [taken])
    c, h = await client(make_app, client_for)
    body = {
        "title": "Escalação confirmada",
        "summary": "Resumo do editor",
        "sport_id": "football",
        "team_ids": [str(team.id)],
        "urls": ["https://novo.example.com/a", "https://taken.example.com/noticia/1"],
    }
    r = await c.post("/api/v1/events", json=body, headers=h)
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["origin"], b["status"], b["relevance"], b["reliability"], b["title_origin"]) == (
        "manual",
        "NEW",
        "MEDIUM",
        "UNKNOWN",
        "human",
    )
    assert {"title", "summary", "sport", "relevance", "entities"} <= set(b["manual_overrides"])
    assert b["skipped_urls"] == [
        {"url": "https://taken.example.com/noticia/1", "event_id": str(other.id)}
    ]
    assert r.headers["ETag"] == '"1"'
    again = await c.post("/api/v1/events", json=body, headers=h)
    assert again.json()["id"] == b["id"]  # Idempotency-Key

    async with db.uow() as u:
        art = (
            await u.session.execute(
                text(
                    "SELECT id FROM ingestion.articles WHERE target_event_id = :e AND original_url LIKE 'https://novo%'"
                ),
                {"e": b["id"]},
            )
        ).scalar()
        await u.session.execute(
            text("UPDATE ingestion.articles SET state='enriched' WHERE id=:i"), {"i": art}
        )
        await u.session.execute(
            text(
                "INSERT INTO intelligence.article_enrichments (article_id, relevance, prompt_version, enriched_at) VALUES (:i, 'LOW', 'rules/v2', now())"
            ),
            {"i": art},
        )
    out = await cluster_article(db, art, SystemClock(), repo_for, find_candidates)
    assert out
    assert (str(out.event_id), out.method.value) == (b["id"], "manual")


async def test_invalid_url_points_to_index(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h = await client(make_app, client_for)
    r = await c.post(
        "/api/v1/events",
        json={"title": "X", "urls": ["https://ok.example.com/1", "ftp://bad"]},
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "urls[1]"
    async with db.uow() as u:
        n = (
            await u.session.execute(text("SELECT count(*) FROM events.events WHERE title = 'X'"))
        ).scalar()
    assert n == 0
