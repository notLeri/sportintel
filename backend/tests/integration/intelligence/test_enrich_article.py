from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from tests.factories import make_article, make_source

from sportintel.modules.ingestion.domain.values import ArticleState
from sportintel.modules.ingestion.infrastructure.repository import SqlArticleRepository
from sportintel.modules.intelligence import public as intelligence
from sportintel.modules.intelligence.application.enrich_article import enrich_article
from sportintel.modules.intelligence.infrastructure.repository import SqlEnrichmentRepository
from sportintel.platform import jobs, settings_store
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration_commit
NOW = datetime(2026, 10, 8, 15, tzinfo=UTC)


@pytest.fixture
async def db(committing_db: Database) -> AsyncIterator[Database]:
    settings_store.clear_cache()
    yield committing_db
    async with committing_db.uow() as u:
        await u.session.execute(text("DELETE FROM ingestion.articles"))
        await u.session.execute(
            text("DELETE FROM sources.sources WHERE domain LIKE '%.example.com'")
        )


async def extracted(db: Database, **kw):  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        src = await make_source(u, domain=kw.pop("domain", "enr.example.com"))
        a = await make_article(u, src, **kw)
        await SqlArticleRepository(u.session).set_state(a.id, ArticleState.EXTRACTED, NOW)
    return a


async def run(db: Database, article_id):  # type: ignore[no-untyped-def]
    return await enrich_article(
        db,
        lambda u: SqlEnrichmentRepository(u.session),
        article_id,
        FrozenClock(NOW),
        llm_available=False,
    )


async def test_rules_enrichment_saved_and_cluster_enqueued(db: Database) -> None:
    a = await extracted(
        db,
        url="https://enr.example.com/futebol/x",
        title="Flamengo confirma lesão de Pedro antes do clássico",
        lead="Mengão perde o atacante.",
    )
    assert await run(db, a.id) == "HIGH"
    async with db.uow() as u:
        e = await intelligence.get_enrichment(u, a.id)
        state = (
            await u.session.execute(
                text("SELECT state FROM ingestion.articles WHERE id=:i"), {"i": a.id}
            )
        ).scalar()
        jobs_n = (
            await u.session.execute(
                text(
                    "SELECT count(*) FROM procrastinate.procrastinate_jobs WHERE task_name='events.cluster_article'"
                )
            )
        ).scalar()
    assert e is not None
    assert (e.sport_id, e.method, e.embedding) == ("football", "rules", None)
    assert any(x["role"] == "subject" for x in e.entities)
    assert (state, jobs_n) == ("enriched", 1)
    assert await run(db, a.id) is None  # повтор: уже enriched


async def test_syndicated_copy_waits_then_copies(db: Database) -> None:
    orig = await extracted(
        db, domain="orig-enr.example.com", title="Palmeiras define escalação com titulares"
    )
    async with db.uow() as u:
        src = await make_source(u, domain="copy-enr.example.com")
        copy = await make_article(u, src, title="cópia")
        await u.session.execute(
            text("UPDATE ingestion.articles SET duplicate_of=:o, state='extracted' WHERE id=:c"),
            {"o": orig.id, "c": copy.id},
        )
    with pytest.raises(jobs.TransientError):
        await run(db, copy.id)
    await run(db, orig.id)
    assert await run(db, copy.id) == "copied"
    async with db.uow() as u:
        got = await intelligence.get_enrichments(u, [orig.id, copy.id])
    assert got[copy.id].relevance == got[orig.id].relevance
