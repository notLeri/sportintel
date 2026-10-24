from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from tests.factories import make_source

from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.ingestion.application.preview_fetch import preview_fetch
from sportintel.modules.ingestion.infrastructure.parsers import get_profile
from sportintel.modules.ingestion.jobs import extract_with_profile
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database
from sportintel.platform.safe_fetch import FakeHttpFetcher, FetchError, PoliteFetcher
from sportintel.platform.safe_fetch.fake import ok

pytestmark = pytest.mark.integration_commit
FIX = Path(__file__).resolve().parents[3].parent / "fixtures" / "sources" / "default"
FEED = "https://ge.globo.com/rss/preview/"
FIRST = "https://ge.globo.com/futebol/times/flamengo/noticia/2026/10/07/flamengo-confirma-lesao-de-pedro.ghtml"
CLOCK = FrozenClock(datetime(2026, 10, 7, 15, tzinfo=UTC))


async def _no_sleep(_: float) -> None:
    return None


async def test_preview_lists_items_and_sample_without_saving(committing_db: Database) -> None:
    db = committing_db
    async with db.uow() as u:
        src = await make_source(
            u,
            domain="globo.com",
            base_url="https://ge.globo.com",
            feed_urls=[FEED, "https://ge.globo.com/404"],
        )
        before = (await u.session.execute(text("SELECT count(*) FROM ingestion.articles"))).scalar()
        pid = await ingestion.start_preview(u, src.id, None)
    fake = FakeHttpFetcher(
        {
            FEED: ok(FEED, (FIX / "rss_ge.xml").read_bytes()),
            "https://ge.globo.com/404": FetchError("fetch_http_4xx", "HTTP 404", permanent=True),
            FIRST: ok(
                FIRST, (FIX / "pages" / "ge_article.html").read_bytes(), content_type="text/html"
            ),
        }
    )
    await preview_fetch(
        db, pid, PoliteFetcher(fake, db, CLOCK, sleep=_no_sleep), get_profile, extract_with_profile
    )
    async with db.uow() as u:
        res = await ingestion.get_preview(u, pid)
        after = (await u.session.execute(text("SELECT count(*) FROM ingestion.articles"))).scalar()
        await u.session.execute(text("DELETE FROM ingestion.preview_results"))
        await u.session.execute(text("DELETE FROM sources.sources WHERE id = :i"), {"i": src.id})
    assert res
    assert res["status"] == "ok"
    feeds = res["result"]["feeds"]
    assert (feeds[0]["status"], len(feeds[0]["items"])) == ("ok", 10)
    assert (feeds[1]["status"], feeds[1]["error_code"]) == ("error", "fetch_http_4xx")
    assert res["result"]["sample"]["text_chars"] > 100
    assert after == before
