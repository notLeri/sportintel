"""Задача ingestion.fetch_source: опрос лент источника и новые статьи (BE-T1.6)."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

import structlog

from sportintel.modules.ingestion.application.dto import FetchSummary
from sportintel.modules.ingestion.domain.article import (
    TITLE_MAX,
    NewArticle,
    clip_words,
    html_to_text,
)
from sportintel.modules.ingestion.domain.feed_item import FeedItem
from sportintel.modules.ingestion.domain.url import canonicalize
from sportintel.modules.sources import public as sources
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.ids import new_id
from sportintel.platform.jobs import TransientError
from sportintel.platform.safe_fetch import FetchError, FetchRequest, FetchResponse
from sportintel.platform.safe_fetch.port import Accept

# ponytail: константы вместо app_settings.content.lead_max_chars и порога старых лент;
# переедут в settings_store в BE-T2.3 (core).
LEAD_MAX_CHARS = 500
MAX_ITEM_AGE = timedelta(days=7)
FUTURE_TOLERANCE = timedelta(hours=1)
_log = structlog.get_logger("sportintel.ingestion")


class Fetcher(Protocol):
    async def fetch(self, req: FetchRequest, *, min_gap_ms: int) -> FetchResponse: ...


class ArticleStore(Protocol):
    async def insert_new(self, items: list[NewArticle], now: datetime) -> list[uuid.UUID]: ...


class Profile(Protocol):
    @property
    def empty_list_is_error(self) -> bool: ...
    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]: ...


def _belongs(url: str, domain: str) -> bool:
    host = sources.normalize_domain(url)
    return host == domain or host.endswith("." + domain)


def to_new_article(
    item: FeedItem, meta: sources.SourceMeta, now: datetime, future_ok: bool = False
) -> NewArticle | None:
    """future_ok — календарь праздников: дата праздника впереди и это не ошибка ленты."""
    try:
        canonical = canonicalize(item.url, frozenset(meta.url_keep_params))
    except ValueError:
        return None
    if not _belongs(canonical, meta.domain):
        _log.info("ingestion.foreign_item_skipped", source_id=str(meta.id))
        return None
    published = item.published_at
    if published is not None and not future_ok and published > now + FUTURE_TOLERANCE:
        published = None  # некорректная дата в ленте (§11)
    if published is not None and published < now - MAX_ITEM_AGE:
        return None
    lead = clip_words(html_to_text(item.summary), LEAD_MAX_CHARS) if item.summary else None
    return NewArticle(
        source_id=meta.id,
        canonical_url=canonical,
        original_url=item.url,
        title=clip_words(item.title, TITLE_MAX),
        lead=lead or None,
        published_at=published,
        image_url=item.image_url,
        author=(item.author or "")[:200] or None,
    )


def expand_years(urls: tuple[str, ...], now: datetime, lead: timedelta | None) -> list[str]:
    """{year} в адресе ленты календаря — текущий год и, на стыке лет, следующий."""
    years = sorted({now.year, (now + (lead or timedelta())).year})
    return [u.replace("{year}", str(y)) for u in urls for y in (years if "{year}" in u else [0])]


async def fetch_source(
    db: Database,
    store_for: Callable[[UnitOfWork], ArticleStore],
    source_id: uuid.UUID,
    fetcher: Fetcher,
    clock: Clock,
    profile_for: Callable[[str], Profile],
) -> FetchSummary:
    summary = FetchSummary()
    async with db.uow() as uow:
        try:
            meta = await sources.get_source_meta(uow, source_id)
        except Exception:
            meta = None
        if meta is None:
            summary.skipped = True
            return summary
        if not meta.active or meta.kind == "manual":
            summary.skipped = True
            await _run(uow, source_id, None, clock.now(), clock.now(), "skipped")
            return summary
        cache = await sources.get_feed_cache(uow, source_id)
    profile = profile_for(meta.parser_profile)
    # calendar — JSON API или HTML-страница с официальными праздниками
    accept: Accept = {"html": "html", "calendar": "any"}.get(meta.kind, "feed")  # type: ignore[assignment]
    lead = getattr(profile, "max_lead", None)  # праздники: только ближайшие дни

    transient_only = True
    for feed_url in expand_years(meta.feed_urls, clock.now(), lead):
        summary.feeds += 1
        started = clock.now()
        cached = cache.get(feed_url) or {}
        try:
            response = await fetcher.fetch(
                FetchRequest(
                    feed_url,
                    accept,
                    etag=cached.get("etag"),
                    last_modified=cached.get("last_modified"),
                ),
                min_gap_ms=meta.min_request_gap_ms,
            )
        except FetchError as e:
            summary.errors += 1
            summary.error_codes.append(e.code)
            transient_only = transient_only and not e.permanent
            async with db.uow() as uow:
                await _run(
                    uow,
                    source_id,
                    feed_url,
                    started,
                    clock.now(),
                    "error",
                    error_code=e.code,
                    error_detail=e.detail,
                )
            continue

        if response.not_modified:
            summary.not_modified += 1
            async with db.uow() as uow:
                await _run(
                    uow, source_id, feed_url, started, clock.now(), "not_modified", http_status=304
                )
            continue

        try:
            items = await asyncio.to_thread(
                profile.list_items, response.body, response.content_type, response.final_url
            )
            if not items and profile.empty_list_is_error:
                raise ValueError("list page returned no items (layout changed?)")
        except Exception as e:  # битая лента без элементов / сломанный профиль
            summary.errors += 1
            summary.error_codes.append("extract_empty")
            transient_only = False
            async with db.uow() as uow:
                await _run(
                    uow,
                    source_id,
                    feed_url,
                    started,
                    clock.now(),
                    "error",
                    http_status=response.status,
                    error_code="extract_empty",
                    error_detail=str(e),
                )
            continue

        now = clock.now()
        if lead is not None:
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            items = [i for i in items if i.published_at and today <= i.published_at <= now + lead]
        candidates = [
            a
            for a in (to_new_article(i, meta, now, future_ok=lead is not None) for i in items)
            if a is not None
        ]
        async with db.uow() as uow:
            created = await store_for(uow).insert_new(candidates, now)
            for article_id in created:
                uow.enqueue_after_commit(
                    "ingestion.extract_article",
                    queueing_lock=f"extract:{article_id}",
                    article_id=str(article_id),
                )
            await sources.set_feed_cache_entry(
                uow, source_id, feed_url, response.etag, response.last_modified
            )
            await _run(
                uow,
                source_id,
                feed_url,
                started,
                clock.now(),
                "ok",
                http_status=response.status,
                items_seen=len(items),
                items_new=len(created),
            )
        summary.ok += 1
        summary.items_seen += len(items)
        summary.items_new += len(created)

    healthy = summary.ok + summary.not_modified > 0
    async with db.uow() as uow:
        await sources.mark_fetch_result(uow, source_id, healthy, summary.items_new, clock.now())
    _log.info(
        "ingestion.source_fetched",
        source_id=str(source_id),
        new=summary.items_new,
        errors=summary.errors,
    )
    if not healthy and summary.errors and transient_only:
        # После записи runs: задача повторится по RetryPolicy (§7, шаг 5).
        raise TransientError(f"all feeds failed transiently: {summary.error_codes}")
    return summary


async def _run(
    uow: UnitOfWork,
    source_id: uuid.UUID,
    feed_url: str | None,
    started: datetime,
    finished: datetime,
    status: sources.RunStatus,
    **kw: object,
) -> None:
    await sources.record_fetch_run(
        uow,
        sources.FetchRunRecord(
            id=new_id(),
            source_id=source_id,
            feed_url=feed_url,
            started_at=started,
            finished_at=finished,
            status=status,
            **kw,  # type: ignore[arg-type]
        ),
    )
