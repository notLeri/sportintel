"""Вежливость к источникам: robots.txt и интервал между запросами к хосту (BE-T1.4)."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import structlog

from sportintel.platform.clock import Clock
from sportintel.platform.db import Database
from sportintel.platform.safe_fetch.errors import FetchError
from sportintel.platform.safe_fetch.port import FetchRequest, FetchResponse, HttpFetcher

ROBOTS_UA = "SportIntelBot"
ROBOTS_MISSING_TTL_S = 3600
MIN_GAP_MS = 500
_log = structlog.get_logger("sportintel.safe_fetch")


class PoliteFetcher:
    """Обёртка над HttpFetcher для ingestion: robots.txt всегда, кроме загрузки самого robots.txt.

    ponytail: интервал между процессами — только сериализация advisory lock'ом; при > 1
    worker-процесса возможны два запроса подряд без паузы. Добавить таблицу
    platform.host_last_request, если worker станет больше одного.
    """

    def __init__(
        self,
        inner: HttpFetcher,
        db: Database,
        clock: Clock,
        robots_ttl_s: int = 86400,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.inner = inner
        self.db = db
        self.clock = clock
        self.robots_ttl_s = robots_ttl_s
        self.sleep = sleep
        self._robots: dict[str, tuple[RobotFileParser | None, float]] = {}
        self._last_request_at: dict[str, float] = {}

    async def fetch(
        self, req: FetchRequest, *, min_gap_ms: int, respect_robots: bool = True
    ) -> FetchResponse:
        if min_gap_ms < MIN_GAP_MS:
            raise ValueError(f"min_gap_ms must be >= {MIN_GAP_MS}")
        host = (urlsplit(req.url).hostname or "").lower()
        gap_ms = min_gap_ms
        if respect_robots:
            parser = await self._robots_for(req.url)
            if parser is not None:
                if not parser.can_fetch(ROBOTS_UA, req.url):
                    raise FetchError(
                        "blocked_by_robots", f"robots.txt disallows {req.url}", permanent=True
                    )
                delay = parser.crawl_delay(ROBOTS_UA)
                if delay:
                    gap_ms = max(gap_ms, int(float(delay) * 1000))

        # Advisory lock сериализует запросы к хосту между воркерами на время запроса (≤ 10 с).
        async with self.db.uow() as uow:
            await uow.advisory_xact_lock(f"host:{host}")
            last = self._last_request_at.get(host)
            if last is not None:
                wait = last + gap_ms / 1000 - self._now()
                if wait > 0:
                    await self.sleep(wait)
            try:
                return await self.inner.fetch(req)
            finally:
                self._last_request_at[host] = self._now()

    def _now(self) -> float:
        return self.clock.now().timestamp()

    async def _robots_for(self, url: str) -> RobotFileParser | None:
        """Парсер robots.txt хоста или None — «разрешено всё» (нет файла или ошибка)."""
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}".lower()
        cached = self._robots.get(key)
        now = time.monotonic()
        if cached and cached[1] > now:
            return cached[0]
        robots_url = f"{key}/robots.txt"
        parser: RobotFileParser | None
        ttl = self.robots_ttl_s
        try:
            resp = await self.inner.fetch(FetchRequest(robots_url, "any", max_bytes=500_000))
            # ponytail: urllib.robotparser понимает не все расширения (wildcards частично).
            parser = RobotFileParser(robots_url)
            parser.parse(resp.body.decode("utf-8", errors="replace").splitlines())
        except FetchError as e:
            _log.info("platform.robots_unavailable", host=parts.hostname, code=e.code)
            parser, ttl = None, ROBOTS_MISSING_TTL_S
        self._robots[key] = (parser, now + ttl)
        return parser


__all__ = ["PoliteFetcher"]
