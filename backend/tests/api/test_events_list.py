from datetime import UTC, datetime, timedelta

import pytest
from tests.api.conftest import dev_login
from tests.factories import make_article, make_entity, make_event, make_source

from sportintel.modules.events.domain.values import AssessmentOrigin, Relevance, RelevanceAssessment
from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


def rel(level: str) -> RelevanceAssessment:
    return RelevanceAssessment(Relevance(level), "r", AssessmentOrigin.RULE)


async def seed(db: Database):  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s1, s2 = (
            await make_source(u, domain="evl1.example.com"),
            await make_source(u, domain="evl2.example.com"),
        )
        ent = await make_entity(u, "Lista Ent")
        out = {}
        for key, level, sport, hours, src in [
            ("hot", "HIGH", "football", 2, s1),
            ("old", "HIGH", "football", 48, s1),
            ("mid", "MEDIUM", "football", 3, s2),
            ("volley", "HIGH", "volleyball", 1, s1),
            ("none", "LOW", None, 5, s2),
            ("junk", "IRRELEVANT", None, 1, s1),
        ]:
            a = await make_article(u, src)
            ev = await make_event(
                u,
                [a],
                title=f"Evento {key}",
                relevance=rel(level),
                sport_id=sport,
                last_article_at=NOW - timedelta(hours=hours),
                source_ids=[src.id],
            )
            out[key] = ev
        await SqlEventRepository(u.session).replace_entities(
            out["mid"].id, [(ent.id, "team", 1, False)]
        )
    return out, s2, ent


async def client(make_app, client_for):  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    await dev_login(c, "events-reader@corp.com", "researcher")
    return c


def titles(resp) -> list[str]:  # type: ignore[no-untyped-def]
    assert resp.status_code == 200, resp.text
    return [i["title"] for i in resp.json()["items"]]


async def test_filters(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    _, s2, ent = await seed(db)
    c = await client(make_app, client_for)
    since = (NOW - timedelta(hours=24)).isoformat()
    r = await c.get(
        "/api/v1/events", params={"sport": "football", "relevance": "HIGH", "from": since}
    )
    assert titles(r) == ["Evento hot"]
    assert "X-Server-Time" in r.headers
    assert "Evento junk" not in titles(await c.get("/api/v1/events", params={"limit": 100}))
    assert titles(await c.get("/api/v1/events", params={"relevance": "IRRELEVANT"})) == [
        "Evento junk"
    ]
    assert titles(await c.get("/api/v1/events", params={"sport": "none"})) == ["Evento none"]
    assert set(titles(await c.get("/api/v1/events", params={"source": str(s2.id)}))) == {
        "Evento mid",
        "Evento none",
    }
    excluded = set(titles(await c.get("/api/v1/events", params={"source_exclude": str(s2.id)})))
    assert excluded
    assert not excluded & {"Evento mid", "Evento none"}
    assert titles(await c.get("/api/v1/events", params={"entity": str(ent.id)})) == ["Evento mid"]
    item = (await c.get("/api/v1/events", params={"entity": str(ent.id)})).json()["items"][0]
    assert item["top_sources"][0]["id"] == str(s2.id)
    assert (await c.get("/api/v1/events", params={"status": "NOPE"})).status_code == 422
    future = (NOW + timedelta(days=3650)).isoformat()
    assert titles(await c.get("/api/v1/events", params={"updated_since": future})) == []


async def test_pagination_both_sorts_no_duplicates(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    await seed(db)
    c = await client(make_app, client_for)
    for sort in ("rank", "recent"):
        seen, cursor = [], None
        for _ in range(10):
            params = {"sort": sort, "limit": 2, **({"cursor": cursor} if cursor else {})}
            body = (await c.get("/api/v1/events", params=params)).json()
            seen += [i["id"] for i in body["items"]]
            cursor = body["next_cursor"]
            if not cursor:
                break
        assert len(seen) == len(set(seen)) >= 5
    rank_cursor = (await c.get("/api/v1/events", params={"sort": "rank", "limit": 1})).json()[
        "next_cursor"
    ]
    assert (
        await c.get("/api/v1/events", params={"sort": "recent", "cursor": rank_cursor})
    ).status_code == 422
