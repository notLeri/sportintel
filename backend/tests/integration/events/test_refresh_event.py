from datetime import UTC, datetime

from sqlalchemy import text
from tests.factories import make_article, make_entity, make_event, make_source

from sportintel.modules.events.application.refresh_event import refresh_event
from sportintel.modules.events.domain.actor import SYSTEM
from sportintel.modules.events.domain.values import Reliability
from sportintel.modules.events.jobs import repo_for
from sportintel.modules.sources.domain.values import SourceTier
from sportintel.platform import settings_store
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database

CLOCK = FrozenClock(datetime(2026, 10, 8, 15, tzinfo=UTC))


async def enrich(u, a, ents, sport="football"):  # type: ignore[no-untyped-def]
    await u.session.execute(
        text(
            "INSERT INTO intelligence.article_enrichments (article_id, sport_id, relevance, headline, prompt_version, enriched_at)"
            " VALUES (:i, :s, 'MEDIUM', '', 'rules/v1', now())"
        ),
        {"i": a.id, "s": sport},
    )
    for e in ents:
        await u.session.execute(
            text(
                "INSERT INTO intelligence.article_entities (article_id, entity_id, role) VALUES (:a, :e, 'subject')"
            ),
            {"a": a.id, "e": e.id},
        )


async def test_refresh_official_override_empty_diff_and_related(db: Database) -> None:
    settings_store.clear_cache()
    async with db.uow() as u:
        ge = await make_source(
            u, domain="rf-ge.example.com", tier=SourceTier.A, owner_group="globo"
        )
        cbf = await make_source(
            u, domain="rf-cbf.example.com", tier=SourceTier.OFFICIAL, owner_group="cbf"
        )
        t1, t2 = await make_entity(u, "Refresh Um"), await make_entity(u, "Refresh Dois")
        a1 = await make_article(
            u, ge, title="Lesão no Flamengo", lead="Pedro sai. Volta em um mês."
        )
        a2 = await make_article(u, cbf, title="CBF confirma lesão")
        await enrich(u, a1, [t1, t2])
        await enrich(u, a2, [t1, t2])
        ev = await make_event(u, [a1])
        other = await make_event(u, [await make_article(u, ge)])
        await repo_for(u).replace_entities(
            other.id, [(t1.id, "team", 1, False), (t2.id, "team", 1, False)]
        )
        ev_db = await repo_for(u).get(ev.id)
        assert ev_db
        ev_db.edit(SYSTEM, CLOCK.now(), sport_id="volleyball")
        await repo_for(u).save(ev_db, 1)

        assert await refresh_event(db, ev.id, CLOCK, repo_for)
        got = await repo_for(u).get(ev.id)
        assert got
        assert (got.reliability.level, got.sport_id, got.title, got.summary) == (
            Reliability.MEDIUM,
            "volleyball",
            "Lesão no Flamengo",
            "Pedro sai. Volta em um mês.",
        )
        assert got.has_updates_since_edit
        assert got.refresh_requested_at is None
        version = got.version
        assert not await refresh_event(db, ev.id, CLOCK, repo_for)  # пустой diff
        assert (await repo_for(u).get(ev.id)).version == version  # type: ignore[union-attr]

        from sportintel.modules.events.domain.values import ArticleLink, AttachMethod

        got.attach(ArticleLink(a2.id, CLOCK.now(), 0.9, AttachMethod.AUTO), CLOCK.now())
        await repo_for(u).save(got, version)
        await refresh_event(db, ev.id, CLOCK, repo_for)
        final = await repo_for(u).get(ev.id)
        assert final
        assert (final.reliability.level, final.title) == (Reliability.HIGH, "CBF confirma lesão")
        rel = (
            (
                await u.session.execute(
                    text(
                        "SELECT related_event_id FROM events.event_relations WHERE event_id=:i AND kind='related'"
                    ),
                    {"i": ev.id},
                )
            )
            .scalars()
            .all()
        )
        assert rel == [other.id]
