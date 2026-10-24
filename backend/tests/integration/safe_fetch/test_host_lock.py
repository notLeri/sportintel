import asyncio

import pytest

from sportintel.platform.clock import SystemClock
from sportintel.platform.db import Database
from sportintel.platform.safe_fetch import FetchRequest, FetchResponse, PoliteFetcher
from sportintel.platform.safe_fetch.fake import ok

pytestmark = pytest.mark.integration_commit
URL = "https://slow.example.com/feed.xml"


class SlowFetcher:
    """Фиксирует перекрытие запросов к одному хосту."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def fetch(self, req: FetchRequest) -> FetchResponse:
        if req.url.endswith("/robots.txt"):
            return ok(req.url, "", "text/plain")
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.2)
        self.active -= 1
        return ok(req.url, "<rss/>")


async def test_parallel_requests_to_one_host_are_serialized(pg_container: str) -> None:
    db = Database(pg_container, pool_size=4)
    inner = SlowFetcher()
    # Два «воркера» = два PoliteFetcher (у каждого свой in-process state) на одной БД.
    a, b = (PoliteFetcher(inner, db, SystemClock()) for _ in range(2))
    try:
        await asyncio.gather(
            a.fetch(FetchRequest(URL, "feed"), min_gap_ms=500),
            b.fetch(FetchRequest(URL, "feed"), min_gap_ms=500),
        )
    finally:
        await db.dispose()
    assert inner.max_active == 1
