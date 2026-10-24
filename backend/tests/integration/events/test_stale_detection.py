from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from tests.factories import make_article, make_event, make_source

from sportintel.modules.events.application.refresh_event import refresh_event
from sportintel.modules.events.jobs import repo_for
from sportintel.platform import settings_store
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
TITLE = "Pedro renova contrato com o Flamengo até 2028"


async def test_republished_week_old_story_is_stale(db: Database) -> None:
    settings_store.clear_cache()
    async with db.uow() as u:
        s = await make_source(u)
        old = await make_event(
            u, [await make_article(u, s, title=TITLE)], now=NOW - timedelta(days=8)
        )
        a = await make_article(u, s, title=TITLE, published_at=NOW)
        await u.session.execute(
            text(
                "INSERT INTO intelligence.article_enrichments (article_id, sport_id, relevance, relevance_rationale, prompt_version, enriched_at)"
                " VALUES (:i, 'football', 'HIGH', 'rules: x', 'rules/v2', now())"
            ),
            {"i": a.id},
        )
        fresh = await make_event(u, [a], now=NOW)
    assert await refresh_event(db, fresh.id, FrozenClock(NOW), repo_for)
    async with db.uow() as u:
        e = await repo_for(u).get(fresh.id)
        rel = (
            (
                await u.session.execute(
                    text(
                        "SELECT related_event_id FROM events.event_relations WHERE event_id=:i AND kind='old_news'"
                    ),
                    {"i": fresh.id},
                )
            )
            .scalars()
            .all()
        )
    assert e
    assert e.stale_suspected
    assert rel == [old.id]
    assert e.relevance.level.value == "MEDIUM"
    assert e.relevance.rationale.endswith(" · stale")
