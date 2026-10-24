"""Публичный фасад модуля ingestion. Другие модули импортируют только отсюда."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sportintel.modules.ingestion.api.router import router
from sportintel.modules.ingestion.infrastructure.parsers import REGISTRY
from sportintel.modules.ingestion.infrastructure.parsers.telegram_page import parse_channel_page
from sportintel.modules.ingestion.infrastructure.repository import SqlArticleRepository
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import NotFound

__all__ = [
    "ArticleForEnrichment",
    "ArticleMeta",
    "add_manual_url",
    "count_recent_by_source",
    "failure_summary",
    "get_article_for_enrichment",
    "get_articles_meta",
    "get_preview",
    "ingest_lag_p95",
    "list_failed",
    "mark_state",
    "parser_profiles",
    "retry_failed",
    "router",
    "start_preview",
    "stuck_articles",
    "telegram_channel_page",
]


def telegram_channel_page(page: bytes) -> dict[str, Any]:
    """Шапка и сообщения со страницы t.me/s/<канал> с разметкой — превью канала в UI."""
    return parse_channel_page(page)


def parser_profiles() -> list[str]:
    """Имена профилей для валидации источников (sources не импортирует ingestion)."""
    return sorted(REGISTRY)


@dataclass(frozen=True)
class ArticleForEnrichment:
    id: uuid.UUID
    source_id: uuid.UUID
    title: str
    lead: str | None
    text: str | None  # None — snippet_only, paywall или истёк TTL
    published_at: datetime | None
    language: str | None
    url: str
    state: str = "discovered"
    duplicate_of: uuid.UUID | None = None
    target_event_id: uuid.UUID | None = None
    discovered_at: datetime | None = None


async def get_article_for_enrichment(
    uow: UnitOfWork, article_id: uuid.UUID, clock: Clock
) -> ArticleForEnrichment:
    repo = SqlArticleRepository(uow.session)
    article = await repo.get(article_id)
    if article is None:
        raise NotFound(f"article {article_id} not found")
    return ArticleForEnrichment(
        id=article.id,
        source_id=article.source_id,
        title=article.title,
        lead=article.lead,
        text=await repo.get_text(article_id, clock.now()),
        published_at=article.published_at,
        language=article.language,
        url=article.original_url,
        state=article.state.value,
        duplicate_of=article.duplicate_of,
        target_event_id=article.target_event_id,
        discovered_at=article.discovered_at,
    )


async def mark_state(
    uow: UnitOfWork,
    article_id: uuid.UUID,
    state: str,
    clock: Clock,
    failure_code: str | None = None,
) -> None:
    from sportintel.modules.ingestion.domain.values import ArticleState

    await SqlArticleRepository(uow.session).set_state(
        article_id, ArticleState(state), clock.now(), failure_code
    )


async def stuck_articles(
    uow: UnitOfWork, state: str, before: datetime, limit: int = 500
) -> list[uuid.UUID]:
    """Для правил сверки других модулей (CONV §10)."""
    from sportintel.modules.ingestion.domain.values import ArticleState

    return await SqlArticleRepository(uow.session).stuck_in_state(
        ArticleState(state), before, limit
    )


@dataclass(frozen=True)
class ArticleMeta:
    id: uuid.UUID
    source_id: uuid.UUID
    title: str
    lead: str | None
    published_at: datetime | None
    discovered_at: datetime
    url: str = ""
    manual: bool = False
    image_url: str | None = None


async def get_articles_meta(uow: UnitOfWork, ids: list[uuid.UUID]) -> dict[uuid.UUID, ArticleMeta]:
    got = await SqlArticleRepository(uow.session).get_many(ids)
    return {
        a.id: ArticleMeta(
            a.id,
            a.source_id,
            a.title,
            a.lead,
            a.published_at,
            a.discovered_at,
            a.original_url,
            a.manual,
            a.image_url,
        )
        for a in got
    }


async def article_translations(
    uow: UnitOfWork, ids: list[uuid.UUID], lang: str
) -> dict[uuid.UUID, dict[str, Any]]:
    """{article_id: {"title", "lead"}} — переводы на язык интерфейса (есть не у всех статей)."""
    return await SqlArticleRepository(uow.session).translations(ids, lang)


async def set_article_translation(
    uow: UnitOfWork, article_id: uuid.UUID, lang: str, title: str, lead: str | None
) -> None:
    await SqlArticleRepository(uow.session).set_translation(article_id, lang, title, lead)


async def add_manual_url(
    uow: UnitOfWork,
    url: str,
    actor_id: uuid.UUID,
    now: datetime,
    target_event_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, bool]:
    """Ручной URL для другого модуля (BE-T3.6). Невалидный URL → article.invalid_url."""
    from sportintel.modules.ingestion.application.ingest_manual_url import ingest_manual_url

    r = await ingest_manual_url(
        uow, SqlArticleRepository(uow.session), url, actor_id, now, target_event_id
    )
    return r.article_id, r.created


# --- Экран пайплайна (BE-T4.12) ---

RETRY_STEP = {  # failure_code → (состояние, задача шага)
    "fetch": ("discovered", "ingestion.extract_article", "extract"),
    "extract": ("discovered", "ingestion.extract_article", "extract"),
    "enrich": ("extracted", "intelligence.enrich_article", "enrich"),
    "cluster": ("enriched", "events.cluster_article", "cluster"),
}
MAX_RETRY = 500


def _step(code: str | None) -> tuple[str, str, str]:
    c = code or ""
    if c.startswith("fetch_") or c in {"ssrf_blocked", "blocked_by_robots", "extract_empty"}:
        return RETRY_STEP["fetch"]
    if c.startswith("enrich_") or c == "budget_exhausted":
        return RETRY_STEP["enrich"]
    if c.startswith("cluster"):
        return RETRY_STEP["cluster"]
    return RETRY_STEP["extract"]


async def failure_summary(uow: UnitOfWork, since: datetime) -> dict[str, Any]:
    from sqlalchemy import text

    states = {
        r[0]: r[1]
        for r in await uow.session.execute(
            text(
                "SELECT state, count(*) FROM ingestion.articles WHERE discovered_at >= :s GROUP BY state"
            ),
            {"s": since},
        )
    }
    codes = [
        {"code": c, "count": n}
        for c, n in await uow.session.execute(
            text(
                "SELECT failure_code, count(*) FROM ingestion.articles WHERE state = 'failed' AND state_changed_at >= :s"
                " GROUP BY failure_code ORDER BY count(*) DESC"
            ),
            {"s": since},
        )
    ]
    lag = (
        await uow.session.execute(
            text(
                "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM discovered_at - published_at))"
                " FROM ingestion.articles WHERE discovered_at >= :s AND published_at IS NOT NULL"
                " AND discovered_at - published_at BETWEEN interval '0' AND interval '24 hours'"
            ),
            {"s": since},
        )
    ).scalar()
    return {
        "states": {
            k: int(states.get(k, 0))
            for k in ("discovered", "extracted", "enriched", "clustered", "failed")
        },
        "failures_by_code": codes,
        "ingest_lag_p95_s": int(lag) if lag is not None else None,
    }


async def list_failed(
    uow: UnitOfWork, code: str | None, after: tuple[datetime, uuid.UUID] | None, limit: int
) -> list[dict[str, Any]]:
    from sqlalchemy import text

    rows = await uow.session.execute(
        text(
            "SELECT id, title, original_url AS url, source_id, failure_code, failure_detail, state_changed_at FROM ingestion.articles"
            " WHERE state = 'failed' AND (CAST(:c AS text) IS NULL OR failure_code = :c)"
            " AND (CAST(:at AS timestamptz) IS NULL OR (state_changed_at, id) < (:at, CAST(:ai AS uuid)))"
            " ORDER BY state_changed_at DESC, id DESC LIMIT :k"
        ),
        {
            "c": code,
            "at": after[0] if after else None,
            "ai": after[1] if after else None,
            "k": limit,
        },
    )
    return [dict(r._mapping) for r in rows]


async def retry_failed(
    uow: UnitOfWork, article_ids: list[uuid.UUID] | None, code: str | None, clock: Clock
) -> tuple[int, int]:
    """Вернуть статьи на шаг по failure_code и поставить задачи. → (повторено, осталось)."""
    from sqlalchemy import text

    rows = (
        await uow.session.execute(
            text(
                "SELECT id, failure_code FROM ingestion.articles WHERE state = 'failed'"
                " AND (CAST(:ids AS uuid[]) IS NULL OR id = ANY(:ids)) AND (CAST(:c AS text) IS NULL OR failure_code = :c)"
                " ORDER BY state_changed_at LIMIT :k FOR UPDATE"
            ),
            {"ids": article_ids, "c": code, "k": MAX_RETRY + 1},
        )
    ).all()
    batch, rest = rows[:MAX_RETRY], max(0, len(rows) - MAX_RETRY)
    now = clock.now()
    for aid, fc in batch:
        state, task, lock = _step(fc)
        await uow.session.execute(
            text(
                "UPDATE ingestion.articles SET state = :st, failure_code = NULL, failure_detail = NULL, state_changed_at = :n WHERE id = :i"
            ),
            {"st": state, "n": now, "i": aid},
        )
        uow.enqueue_after_commit(task, queueing_lock=f"{lock}:{aid}", article_id=str(aid))
    return len(batch), rest


async def ingest_lag_p95(uow: UnitOfWork, since: datetime) -> int | None:
    """p95 (discovered_at − published_at), статьи с лагом 0…24 ч (BE-T4.13)."""
    from sqlalchemy import text

    v = (
        await uow.session.execute(
            text(
                "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM discovered_at - published_at))"
                " FROM ingestion.articles WHERE discovered_at >= :s AND published_at IS NOT NULL"
                " AND discovered_at - published_at BETWEEN interval '0' AND interval '24 hours'"
            ),
            {"s": since},
        )
    ).scalar()
    return int(v) if v is not None else None


# --- Пробный fetch и статистика для админки источников (BE-T4.8) ---


async def start_preview(
    uow: UnitOfWork, source_id: uuid.UUID, actor_id: uuid.UUID | None
) -> uuid.UUID:
    from sqlalchemy import text

    from sportintel.platform.ids import new_id

    pid = new_id()
    await uow.session.execute(
        text(
            "INSERT INTO ingestion.preview_results (id, source_id, requested_by) VALUES (:i, :s, :a)"
        ),
        {"i": pid, "s": source_id, "a": actor_id},
    )
    uow.enqueue_after_commit("ingestion.preview_fetch", preview_id=str(pid))
    return pid


async def get_preview(uow: UnitOfWork, preview_id: uuid.UUID) -> dict[str, Any] | None:
    from sqlalchemy import text

    row = (
        await uow.session.execute(
            text(
                "SELECT id, source_id, status, result, created_at FROM ingestion.preview_results WHERE id = :i"
            ),
            {"i": preview_id},
        )
    ).first()
    return dict(row._mapping) if row else None


async def count_recent_by_source(uow: UnitOfWork, since: datetime) -> dict[uuid.UUID, int]:
    from sqlalchemy import text

    rows = await uow.session.execute(
        text(
            "SELECT source_id, count(*) FROM ingestion.articles WHERE discovered_at >= :s GROUP BY source_id"
        ),
        {"s": since},
    )
    return {s: int(n) for s, n in rows}
