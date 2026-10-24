import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from tests.factories import make_article, make_entity, make_source

from sportintel.modules.events.application.cluster_article import cluster_article
from sportintel.modules.events.jobs import find_candidates, repo_for
from sportintel.platform import jobs, settings_store
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration_commit
NOW = datetime(2026, 10, 8, 15, tzinfo=UTC)
CLOCK = FrozenClock(NOW)


@pytest.fixture
async def db(committing_db: Database) -> AsyncIterator[Database]:
    settings_store.clear_cache()
    yield committing_db
    async with committing_db.uow() as u:
        for sql in (
            "DELETE FROM events.event_articles",
            "DELETE FROM events.events",
            "DELETE FROM ingestion.articles",
            "DELETE FROM sources.sources WHERE domain LIKE '%.example.com'",
        ):
            await u.session.execute(text(sql))


async def enriched(db: Database, title: str, ents: list[uuid.UUID], **kw):  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        src = await make_source(u, domain=kw.pop("domain", f"cl{uuid.uuid4().hex[:6]}.example.com"))
        a = await make_article(u, src, title=title, **kw)
        await u.session.execute(
            text("UPDATE ingestion.articles SET state='enriched' WHERE id=:i"), {"i": a.id}
        )
        await u.session.execute(
            text(
                "INSERT INTO intelligence.article_enrichments (article_id, sport_id, relevance, headline, prompt_version, enriched_at)"
                " VALUES (:i, 'football', 'MEDIUM', :t, 'rules/v1', :n)"
            ),
            {"i": a.id, "t": title, "n": NOW},
        )
        for e in ents:
            await u.session.execute(
                text(
                    "INSERT INTO intelligence.article_entities (article_id, entity_id, role) VALUES (:a, :e, 'subject')"
                ),
                {"a": a.id, "e": e},
            )
    return a


async def run(db: Database, article_id: uuid.UUID):  # type: ignore[no-untyped-def]
    return await cluster_article(db, article_id, CLOCK, repo_for, find_candidates)


async def entities(db: Database, n: int = 2) -> list[uuid.UUID]:
    async with db.uow() as u:
        return [(await make_entity(u, f"Ent {uuid.uuid4().hex[:6]}")).id for _ in range(n)]


async def test_similar_articles_one_event_and_retry_is_noop(db: Database) -> None:
    ents = await entities(db)
    a1 = await enriched(db, "Flamengo confirma lesão de Pedro antes do clássico", ents)
    first = await run(db, a1.id)
    assert first is not None
    assert (first.method.value, first.created) == ("new", True)
    a2 = await enriched(db, "Flamengo confirma lesão de Pedro antes de clássico", ents)
    a3 = await enriched(db, "Flamengo confirma a lesão de Pedro antes do clássico", ents)
    outs = [await run(db, a2.id), await run(db, a3.id)]
    assert [(o.method.value, o.event_id) for o in outs if o] == [("auto", first.event_id)] * 2
    assert await run(db, a3.id) is None
    async with db.uow() as u:
        state = (
            await u.session.execute(
                text("SELECT state FROM ingestion.articles WHERE id=:i"), {"i": a3.id}
            )
        ).scalar()
    assert state == "clustered"


async def test_different_facts_two_events(db: Database) -> None:
    a = await enriched(db, "Palmeiras vence o Santos no Allianz", await entities(db))
    b = await enriched(db, "Seleção feminina convoca goleira para amistoso", await entities(db))
    oa, ob = await run(db, a.id), await run(db, b.id)
    assert oa
    assert ob
    assert oa.event_id != ob.event_id


async def test_concurrent_same_fact_single_event(db: Database) -> None:
    ents = await entities(db)
    a = await enriched(db, "Corinthians anuncia novo técnico para a temporada", ents)
    b = await enriched(db, "Corinthians anuncia novo técnico para a temporada", ents)
    oa, ob = await asyncio.gather(run(db, a.id), run(db, b.id))
    assert oa
    assert ob
    assert oa.event_id == ob.event_id


async def test_syndication_and_manual_target(db: Database) -> None:
    orig = await enriched(db, "Grêmio demite treinador após derrota", await entities(db))
    copy = await enriched(db, "cópia sindicada", [])
    async with db.uow() as u:
        await u.session.execute(
            text("UPDATE ingestion.articles SET duplicate_of=:o WHERE id=:c"),
            {"o": orig.id, "c": copy.id},
        )
    with pytest.raises(jobs.TransientError):
        await run(db, copy.id)
    o = await run(db, orig.id)
    c = await run(db, copy.id)
    assert o
    assert c
    assert (c.method.value, c.event_id) == ("syndication", o.event_id)
    manual = await enriched(db, "Totalmente outro assunto de vôlei", [])
    async with db.uow() as u:
        await u.session.execute(
            text("UPDATE ingestion.articles SET target_event_id=:e WHERE id=:a"),
            {"e": o.event_id, "a": manual.id},
        )
    m = await run(db, manual.id)
    assert m
    assert (m.method.value, m.event_id) == ("manual", o.event_id)
    async with db.uow() as u:
        ev = await repo_for(u).get(o.event_id)
    assert ev
    assert {(lk.method.value, lk.is_duplicate, lk.cluster_locked) for lk in ev.links} == {
        ("new", False, False),
        ("syndication", True, False),
        ("manual", False, True),
    }
