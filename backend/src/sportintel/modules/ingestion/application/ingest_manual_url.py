"""Ручное добавление URL (BE-T1.10). В web-процессе нет сети: SSRF проверит worker."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit

from sportintel.modules.audit import public as audit
from sportintel.modules.ingestion.domain.article import Article, NewArticle
from sportintel.modules.ingestion.domain.url import canonicalize
from sportintel.modules.ingestion.domain.values import ArticleState
from sportintel.modules.sources import public as sources
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import FieldError, ValidationFailed

MAX_URL = 2048


class InvalidUrl(ValidationFailed):
    code = "article.invalid_url"
    title = "Invalid article URL"


@dataclass(frozen=True)
class ManualIngestResult:
    article_id: uuid.UUID
    created: bool
    state: ArticleState


class ManualArticleStore(Protocol):
    async def get_by_canonical(self, canonical_url: str) -> Article | None: ...
    async def insert_new(self, items: list[NewArticle], now: datetime) -> list[uuid.UUID]: ...
    async def set_target_event(self, article_id: uuid.UUID, event_id: uuid.UUID) -> None: ...


def _check(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    if len(url) > MAX_URL or parts.scheme not in {"http", "https"} or not parts.hostname:
        raise InvalidUrl(details=[FieldError("url", "invalid", "http(s) URL with a host, ≤ 2048")])
    try:
        return canonicalize(url)
    except ValueError as e:
        raise InvalidUrl(details=[FieldError("url", "invalid", str(e))]) from None


async def ingest_manual_url(
    uow: UnitOfWork,
    store: ManualArticleStore,
    url: str,
    actor_id: uuid.UUID,
    now: datetime,
    target_event_id: uuid.UUID | None = None,
) -> ManualIngestResult:
    canonical = _check(url)
    existing = await store.get_by_canonical(canonical)
    if existing is not None:
        if target_event_id is not None:
            await store.set_target_event(existing.id, target_event_id)
        return ManualIngestResult(existing.id, False, existing.state)

    domain = sources.normalize_domain(canonical)
    meta = await sources.find_by_domain(uow, domain) or await sources.ensure_manual_source(
        uow, domain
    )
    item = NewArticle(
        source_id=meta.id,
        canonical_url=canonical,
        original_url=url.strip(),
        title=url.strip()[:500],  # временно: заменит extract_article
        lead=None,
        published_at=None,
        image_url=None,
        author=None,
        manual=True,
        added_by=actor_id,
        target_event_id=target_event_id,
    )
    created = await store.insert_new([item], now)
    if not created:  # гонка двух пользователей: статья уже есть
        again = await store.get_by_canonical(canonical)
        assert again is not None  # noqa: S101
        return ManualIngestResult(again.id, False, again.state)
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.ARTICLE_MANUAL_ADDED,
        target_type="article",
        target_id=str(created[0]),
        after={"url": url.strip(), "target_event_id": target_event_id},
    )
    uow.enqueue_after_commit(
        "ingestion.extract_article",
        queueing_lock=f"extract:{created[0]}",
        article_id=str(created[0]),
    )
    return ManualIngestResult(created[0], True, ArticleState.DISCOVERED)
