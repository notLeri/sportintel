"""Задача ingestion.extract_article: текст, метаданные, SimHash, синдикация (BE-T1.7)."""

import asyncio
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

import structlog

from sportintel.modules.ingestion.application.fetch_source import LEAD_MAX_CHARS, Fetcher
from sportintel.modules.ingestion.domain import holiday
from sportintel.modules.ingestion.domain.article import Article, clip_words
from sportintel.modules.ingestion.domain.simhash import simhash64
from sportintel.modules.ingestion.domain.values import ArticleState
from sportintel.modules.sources import public as sources
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.jobs import TransientError
from sportintel.platform.safe_fetch import FetchError, FetchRequest

TEXT_MAX = 200_000
SYNDICATION_WINDOW = timedelta(hours=72)
MAX_URL = 2048
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s")
_log = structlog.get_logger("sportintel.ingestion")


class ExtractedLike(Protocol):
    # property: совместимо с frozen dataclass ExtractedPage (поля только для чтения)
    @property
    def text(self) -> str | None: ...
    @property
    def description(self) -> str | None: ...
    @property
    def published_at(self) -> datetime | None: ...
    @property
    def image_url(self) -> str | None: ...
    @property
    def author(self) -> str | None: ...
    @property
    def language(self) -> str | None: ...


@dataclass(frozen=True)
class _FeedText:
    """Профили, у которых весь текст уже в ленте (API праздников): страницу не качаем."""

    text: str | None
    description: str | None = None
    published_at: datetime | None = None
    image_url: str | None = None
    author: str | None = None
    language: str | None = None


def _feed_only(profile: str) -> bool:
    return profile.startswith("holidays_")  # календари праздников


class ArticleWriter(Protocol):
    async def get(self, article_id: uuid.UUID) -> Article | None: ...
    async def set_state(
        self,
        article_id: uuid.UUID,
        state: ArticleState,
        now: datetime,
        failure_code: str | None = None,
        failure_detail: str | None = None,
    ) -> None: ...
    async def fill_extracted(
        self, article_id: uuid.UUID, fields: dict[str, Any], now: datetime
    ) -> None: ...
    async def save_content(
        self, article_id: uuid.UUID, body: str, now: datetime, ttl: timedelta
    ) -> None: ...
    async def find_syndication_origin(
        self, article_id: uuid.UUID, source_id: uuid.UUID, content_hash: int, since: datetime
    ) -> uuid.UUID | None: ...


def cut_off(lead: str) -> bool:
    """Описание из ленты обрезано на полуслове: «…сосредоточит...», «…tem […]»."""
    return lead.rstrip().endswith(("...", "…", "[…]", "[...]"))


def lead_from_text(text: str, limit: int = LEAD_MAX_CHARS) -> str:
    """Первые предложения, целиком помещающиеся в limit; иначе — обрезка по слову."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    sentences, out = _SENTENCE_END.split(text), ""
    for sentence in sentences:
        if len(out) + len(sentence) + 1 > limit:
            break
        out = f"{out} {sentence}".strip()
    return out or clip_words(text, limit)


def _https_image(url: str | None) -> str | None:
    # http:// — mixed content в UI (BE-T1.7 §11)
    return url if url and url.startswith("https://") and len(url) <= MAX_URL else None


async def extract_article(
    db: Database,
    store_for: Callable[[UnitOfWork], ArticleWriter],
    article_id: uuid.UUID,
    fetcher: Fetcher,
    clock: Clock,
    extract: Callable[[bytes, str, str], ExtractedLike],
) -> ArticleState | None:
    async with db.uow() as uow:
        article = await store_for(uow).get(article_id)
        if article is None or article.state != ArticleState.DISCOVERED:
            return None  # идемпотентность (CONV §15.5)
        meta = await sources.get_source_meta(uow, article.source_id)

    page: ExtractedLike
    if _feed_only(meta.parser_profile):
        page = _FeedText(article.lead)
    else:
        try:
            response = await fetcher.fetch(
                FetchRequest(article.original_url, "html"), min_gap_ms=meta.min_request_gap_ms
            )
        except FetchError as e:
            if not e.permanent:
                raise TransientError(f"{e.code}: {e.detail}") from None
            return await _fail(db, store_for, article_id, clock.now(), e.code, e.detail)

        try:
            page = await asyncio.to_thread(
                extract, response.body, response.final_url, meta.parser_profile
            )
        except Exception as e:
            _log.warning(
                "ingestion.extract_failed", article_id=str(article_id), error=type(e).__name__
            )
            return await _fail(
                db, store_for, article_id, clock.now(), "extract_empty", type(e).__name__
            )

    text = (page.text or "").strip()
    # Лента часто обрезает описание («…сосредоточит...») — тогда лид берётся из текста статьи.
    lead = next((x for x in (article.lead, page.description) if x and not cut_off(x)), None) or (
        lead_from_text(text) if text else article.lead or page.description
    )
    if not text and not lead:
        return await _fail(
            db, store_for, article_id, clock.now(), "extract_empty", "no text and no lead"
        )

    now = clock.now()
    content_hash = simhash64(text or lead or "")
    if _feed_only(meta.parser_profile) and article.published_at is not None:
        # Тот же праздник с другого сайта → совпадёт отпечаток → перепечатка, а не новое событие.
        content_hash = holiday.fingerprint(meta.region, article.published_at.date(), article.title)
    async with db.uow() as uow:
        store = store_for(uow)
        fields: dict[str, Any] = {
            "lead": clip_words(lead, LEAD_MAX_CHARS) if lead else None,
            "replace_lead": bool(article.lead and lead != article.lead),
            "published_at": page.published_at,
            "image_url": _https_image(page.image_url),
            "author": (page.author or "")[:200] or None,
            "language": page.language,
            "content_hash": content_hash,
        }
        page_title = getattr(page, "title", None)
        if article.manual and article.title == article.original_url and page_title:
            fields["title"] = clip_words(page_title, 500)  # временный title = URL (BE-T1.10)
        if content_hash is not None:
            origin = await store.find_syndication_origin(
                article_id, article.source_id, content_hash, now - SYNDICATION_WINDOW
            )
            if origin is not None:
                fields["duplicate_of"] = origin
                _log.info(
                    "ingestion.syndication_found", article_id=str(article_id), origin=str(origin)
                )
        await store.fill_extracted(article_id, fields, now)
        if text and meta.content_policy == "transient_text":
            await store.save_content(
                article_id, text[:TEXT_MAX], now, timedelta(days=meta.content_ttl_days)
            )
        await store.set_state(article_id, ArticleState.EXTRACTED, now)
        # Обработчик регистрирует intelligence (BE-T2.8); Procrastinate хранит задачу до тех пор.
        uow.enqueue_after_commit(
            "intelligence.enrich_article",
            queueing_lock=f"enrich:{article_id}",
            article_id=str(article_id),
        )
    return ArticleState.EXTRACTED


async def _fail(
    db: Database,
    store_for: Callable[[UnitOfWork], ArticleWriter],
    article_id: uuid.UUID,
    now: datetime,
    code: str,
    detail: str,
) -> ArticleState:
    async with db.uow() as uow:
        await store_for(uow).set_state(article_id, ArticleState.FAILED, now, code, detail)
    _log.info("ingestion.article_failed", article_id=str(article_id), code=code)
    return ArticleState.FAILED
