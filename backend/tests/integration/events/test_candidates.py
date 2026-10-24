from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from tests.factories import make_article, make_entity, make_event, make_source

from sportintel.modules.events.infrastructure.candidates import find_candidates
from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.platform.db import Database

AT = datetime(2026, 10, 8, 12, tzinfo=UTC)


async def test_window_sport_entities_and_title(db: Database) -> None:
    async with db.uow() as u:
        s = await make_source(u, domain="cand.example.com")
        fresh = await make_event(
            u,
            [await make_article(u, s)],
            title="Flamengo confirma lesão de Pedro",
            now=AT - timedelta(hours=2),
            sport_id="football",
        )
        old = await make_event(
            u,
            [await make_article(u, s)],
            title="Flamengo confirma lesão de Pedro",
            now=AT - timedelta(hours=100),
            sport_id="football",
        )
        other = await make_event(
            u,
            [await make_article(u, s)],
            title="Flamengo confirma lesão de Pedro",
            now=AT - timedelta(hours=1),
            sport_id="volleyball",
        )
        ents = await make_event(
            u,
            [await make_article(u, s)],
            title="Outro título qualquer",
            now=AT - timedelta(hours=1),
        )
        e1, e2 = await make_entity(u, "Cand Um"), await make_entity(u, "Cand Dois")
        await SqlEventRepository(u.session).replace_entities(
            ents.id, [(e1.id, "team", 1, False), (e2.id, "player", 1, False)]
        )
        await u.session.execute(
            text("UPDATE events.events SET sport_id = NULL WHERE id = :i"), {"i": ents.id}
        )
        got = await find_candidates(
            u.session,
            None,
            {e1.id, e2.id},
            "football",
            AT,
            72,
            20,
            title="Flamengo confirma a lesão de Pedro",
        )
    by_id = {c.event_id: c for c in got}
    assert by_id[fresh.id].lex > 0.5
    assert old.id not in by_id
    assert other.id not in by_id
    assert by_id[ents.id].entity_ids == frozenset({e1.id, e2.id})
    assert by_id[ents.id].cosine is None


async def test_no_signals_no_candidates(db: Database) -> None:
    async with db.uow() as u:
        assert await find_candidates(u.session, None, set(), None, AT, 72, 20) == []


async def test_other_region_is_never_a_candidate(db: Database) -> None:
    async with db.uow() as u:
        s = await make_source(u, domain="cand-region.example.com")
        same = await make_event(
            u, [await make_article(u, s)], title="Benfica vence o clássico", now=AT, sport_id=None
        )
        foreign = await make_event(
            u, [await make_article(u, s)], title="Benfica vence o clássico", now=AT, sport_id=None
        )
        await u.session.execute(
            text(
                "UPDATE events.events SET region = CASE WHEN id = :a THEN 'BR' ELSE 'PT' END"
                " WHERE id IN (:a, :b)"
            ),
            {"a": same.id, "b": foreign.id},
        )
        got = await find_candidates(
            u.session, None, set(), None, AT, 72, 20, title="Benfica vence o clássico", region="BR"
        )
    ids = {c.event_id for c in got}
    assert same.id in ids
    assert foreign.id not in ids
