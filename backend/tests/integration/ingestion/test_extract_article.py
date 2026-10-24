from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from tests.factories import make_article, make_source

from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.ingestion.application.extract_article import extract_article, lead_from_text
from sportintel.modules.ingestion.domain.values import ArticleState
from sportintel.modules.ingestion.infrastructure.repository import SqlArticleRepository
from sportintel.modules.ingestion.jobs import extract_with_profile
from sportintel.modules.sources.domain.values import ContentPolicy
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database
from sportintel.platform.safe_fetch import FakeHttpFetcher, PoliteFetcher
from sportintel.platform.safe_fetch.fake import ok

pytestmark = pytest.mark.integration_commit
PAGES = Path(__file__).resolve().parents[3].parent / "fixtures" / "sources" / "default" / "pages"
NOW = datetime(2026, 10, 7, 18, tzinfo=UTC)


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
async def env(
    committing_db: Database,
) -> AsyncIterator[tuple[Database, FakeHttpFetcher, FrozenClock]]:
    yield committing_db, FakeHttpFetcher(), FrozenClock(NOW)
    async with committing_db.uow() as u:
        await u.session.execute(text("DELETE FROM ingestion.articles"))
        await u.session.execute(
            text("DELETE FROM sources.sources WHERE domain LIKE '%.example.com'")
        )


def page(url: str, name: str):  # type: ignore[no-untyped-def]
    return ok(url, (PAGES / name).read_bytes(), "text/html")


async def run(db, fake, clock, article_id):  # type: ignore[no-untyped-def]
    polite = PoliteFetcher(fake, db, clock, sleep=_no_sleep)
    return await extract_article(
        db,
        lambda u: SqlArticleRepository(u.session),
        article_id,
        polite,
        clock,
        extract_with_profile,
    )


async def load(db: Database, article_id):  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        return await SqlArticleRepository(u.session).get(article_id)


async def test_real_page_fills_fields_and_content(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(u, domain="ge.example.com", content_ttl_days=3)
        art = await make_article(u, source, url="https://ge.example.com/fluminense/cano")
    fake.routes[art.original_url] = page(art.original_url, "ge_article.html")

    assert await run(db, fake, clock, art.id) == ArticleState.EXTRACTED
    got = await load(db, art.id)
    assert got.lead
    assert got.lead.startswith("Cano iniciou")
    assert got.published_at is not None
    assert got.image_url
    assert got.image_url.startswith("https://")
    assert got.content_hash is not None
    async with db.uow() as u:
        exp = (
            await u.session.execute(
                text("SELECT expires_at FROM ingestion.article_content WHERE article_id=:i"),
                {"i": art.id},
            )
        ).scalar()
        for_ai = await ingestion.get_article_for_enrichment(u, art.id, clock)
        jobs = (
            await u.session.execute(
                text(
                    "SELECT count(*) FROM procrastinate.procrastinate_jobs WHERE task_name='intelligence.enrich_article'"
                )
            )
        ).scalar()
    assert exp == NOW + timedelta(days=3)
    assert for_ai.text
    assert len(for_ai.text.split()) > 100
    assert jobs == 1

    assert await run(db, fake, clock, art.id) is None  # повтор для extracted — без изменений


async def test_snippet_only_keeps_no_text(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(
            u, domain="snip.example.com", content_policy=ContentPolicy.SNIPPET_ONLY
        )
        art = await make_article(u, source)
    fake.routes[art.original_url] = page(art.original_url, "cnn_article.html")
    assert await run(db, fake, clock, art.id) == ArticleState.EXTRACTED
    async with db.uow() as u:
        n = (
            await u.session.execute(
                text("SELECT count(*) FROM ingestion.article_content WHERE article_id=:i"),
                {"i": art.id},
            )
        ).scalar()
    assert n == 0
    assert (await load(db, art.id)).lead  # lead всё равно заполнен


async def test_syndication_across_sources(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        a_src, b_src = (
            await make_source(u, domain="orig.example.com"),
            await make_source(u, domain="copy.example.com"),
        )
        first = await make_article(u, a_src, now=NOW - timedelta(hours=2))
        copy = await make_article(u, b_src, now=NOW)
        same_src = await make_article(u, a_src, now=NOW)
    for art in (first, copy, same_src):
        fake.routes[art.original_url] = page(art.original_url, "ge_article_2.html")
    for art in (first, copy, same_src):
        await run(db, fake, clock, art.id)
    assert (await load(db, copy.id)).duplicate_of == first.id
    assert (await load(db, first.id)).duplicate_of is None
    assert (await load(db, same_src.id)).duplicate_of is None  # тот же источник — не синдикация


async def test_404_marks_failed(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(u, domain="gone.example.com")
        art = await make_article(u, source)
    assert await run(db, fake, clock, art.id) == ArticleState.FAILED
    got = await load(db, art.id)
    assert (got.state, got.failure_code) == (ArticleState.FAILED, "fetch_http_4xx")


async def test_paywall_with_rss_lead_is_extracted(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(u, domain="pay.example.com")
        art = await make_article(u, source, lead="Lead do RSS")
    fake.routes[art.original_url] = ok(
        art.original_url, b"<html><body><div>Assine para ler</div></body></html>", "text/html"
    )
    assert await run(db, fake, clock, art.id) == ArticleState.EXTRACTED
    assert (await load(db, art.id)).lead == "Lead do RSS"


async def test_feed_lead_cut_mid_word_is_taken_from_article_text(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(u, domain="cut.example.com")
        art = await make_article(u, source, lead="A lenta do feed para no meio da pala...")
    fake.routes[art.original_url] = page(art.original_url, "ge_article_2.html")
    assert await run(db, fake, clock, art.id) == ArticleState.EXTRACTED
    lead = (await load(db, art.id)).lead or ""
    assert lead
    assert not lead.endswith("...")
    assert "pala..." not in lead


def test_lead_from_text_sentence_boundary() -> None:
    text = "Primeira frase curta. Segunda frase também curta. " + "x" * 600
    assert lead_from_text(text, 60) == "Primeira frase curta. Segunda frase também curta."


async def test_manual_article_title_replaced(env) -> None:  # type: ignore[no-untyped-def]
    db, fake, clock = env
    async with db.uow() as u:
        source = await make_source(u, domain="man.example.com")
        url = "https://man.example.com/x"
        art = await make_article(u, source, url=url, title=url, manual=True)
    fake.routes[url] = page(url, "ge_article.html")
    await run(db, fake, clock, art.id)
    assert (await load(db, art.id)).title.startswith("Cano avança")
