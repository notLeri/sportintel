"""Чтение списка и деталей статей (BE-T1.11)."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.ingestion.infrastructure.tables import articles


@dataclass(frozen=True)
class ArticleFilters:
    source: list[uuid.UUID]
    state: list[str]
    from_: datetime | None
    to: datetime | None
    q: str | None


SORT_TS = func.coalesce(articles.c.published_at, articles.c.discovered_at)
LIST_COLS = [
    articles.c.id,
    articles.c.title,
    articles.c.original_url,
    articles.c.source_id,
    articles.c.published_at,
    articles.c.discovered_at,
    articles.c.state,
    articles.c.failure_code,
    articles.c.manual,
    articles.c.image_url,
]


def _filtered(f: ArticleFilters) -> tuple[Select[Any], Any]:
    q = select(*LIST_COLS)
    if f.source:
        q = q.where(articles.c.source_id.in_(f.source))
    if f.state:
        q = q.where(articles.c.state.in_(f.state))
    if f.from_:
        q = q.where(f.from_ <= SORT_TS)
    if f.to:
        q = q.where(f.to >= SORT_TS)
    rank = None
    if f.q:
        tsq = func.websearch_to_tsquery("pt_unaccent", literal(f.q))  # параметр, не конкатенация
        rank = func.ts_rank(articles.c.search_tsv, tsq)
        q = q.where(articles.c.search_tsv.op("@@")(tsq)).add_columns(rank.label("rank"))
    return q, rank


async def list_page(
    session: AsyncSession, f: ArticleFilters, after: tuple[Any, ...] | None, limit: int
) -> list[dict[str, Any]]:
    q, rank = _filtered(f)
    if rank is None:
        q = q.add_columns(SORT_TS.label("sort_ts"))
        if after:
            q = q.where(
                tuple_(SORT_TS, articles.c.id) < tuple_(literal(after[0]), literal(after[1]))
            )
        q = q.order_by(SORT_TS.desc(), articles.c.id.desc())
    else:
        if after:
            q = q.where(
                tuple_(rank, articles.c.discovered_at, articles.c.id)
                < tuple_(literal(after[0]), literal(after[1]), literal(after[2]))
            )
        q = q.order_by(rank.desc(), articles.c.discovered_at.desc(), articles.c.id.desc())
    return [dict(r._mapping) for r in await session.execute(q.limit(limit))]


async def detail(session: AsyncSession, article_id: uuid.UUID) -> dict[str, Any] | None:
    q = select(
        *LIST_COLS, articles.c.lead, articles.c.author, articles.c.language, articles.c.duplicate_of
    ).where(articles.c.id == article_id)
    row = (await session.execute(q)).first()
    return dict(row._mapping) if row else None
