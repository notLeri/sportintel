"""Чтение списка событий (BE-T2.21; поиск q — BE-T2.22)."""

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    ColumnElement,
    Integer,
    Select,
    exists,
    func,
    literal,
    or_,
    select,
    text,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.events.infrastructure.tables import (
    event_articles,
    event_entities,
    event_relations,
    events,
)

Sort = Literal["rank", "recent", "q"]
e = events.c


@dataclass(frozen=True)
class EventFilters:
    sport: list[str] = field(default_factory=list)
    region: list[str] = field(default_factory=list)
    competition: list[uuid.UUID] = field(default_factory=list)
    relevance: list[str] = field(default_factory=list)
    reliability: list[str] = field(default_factory=list)
    source: list[uuid.UUID] = field(default_factory=list)
    source_exclude: list[uuid.UUID] = field(default_factory=list)
    status: list[str] = field(default_factory=list)
    entity: list[uuid.UUID] = field(default_factory=list)
    from_: datetime | None = None
    to: datetime | None = None
    conflicts: bool | None = None
    q: str | None = None
    updated_since: datetime | None = None
    q_entity_ids: list[uuid.UUID] = field(default_factory=list)  # taxonomy.search_entities(q)


LIST_COLS = [
    e.id,
    e.title,
    e.title_origin,
    e.title_i18n,
    e.relevance,
    e.relevance_origin,
    e.reliability,
    e.reliability_origin,
    e.status,
    e.sport_id,
    e.region,
    e.competition_id,
    e.article_count,
    e.source_count,
    e.independent_source_count,
    e.source_ids,
    e.occurred_at,
    e.last_article_at,
    e.updated_at,
    e.has_open_conflicts,
    e.has_updates_since_edit,
    e.stale_suspected,
    e.has_clickbait,
    e.assignee_id,
    e.origin,
    e.version,
    e.relevance_rank,
]


def _where(f: EventFilters) -> list[ColumnElement[bool]]:
    w: list[ColumnElement[bool]] = []
    w.append(e.relevance.in_(f.relevance) if f.relevance else e.relevance != "IRRELEVANT")
    if f.sport:
        named = [s for s in f.sport if s != "none"]
        conds: list[ColumnElement[bool]] = [e.sport_id.in_(named)] if named else []
        if "none" in f.sport:
            conds.append(e.sport_id.is_(None))
        w.append(or_(*conds))
    for col, vals in (
        (e.competition_id, f.competition),
        (e.region, f.region),
        (e.reliability, f.reliability),
        (e.status, f.status),
    ):
        if vals:
            w.append(col.in_(vals))
    if f.source:
        w.append(e.source_ids.overlap(literal(f.source, type_=e.source_ids.type)))
    if f.source_exclude:  # скрыть события, у которых все источники исключены
        w.append(~e.source_ids.contained_by(literal(f.source_exclude, type_=e.source_ids.type)))
    if f.entity:
        w.append(
            exists().where(
                event_entities.c.event_id == e.id, event_entities.c.entity_id.in_(f.entity)
            )
        )
    if f.from_:
        w.append(e.last_article_at >= f.from_)
    if f.to:
        w.append(e.last_article_at <= f.to)
    if f.conflicts:
        w.append(e.has_open_conflicts.is_(True))
    if f.updated_since:
        w.append(e.updated_at > f.updated_since)
    return w


async def list_page(
    session: AsyncSession, f: EventFilters, sort: Sort, after: tuple[Any, ...] | None, limit: int
) -> list[dict[str, Any]]:
    q: Select[Any] = select(*LIST_COLS).where(*_where(f))
    key: tuple[ColumnElement[Any], ...]
    if f.q:  # BE-T2.22: FTS ∪ совпадение сущностей; sort игнорируется
        tsq = func.websearch_to_tsquery("pt_unaccent", literal(f.q))
        fts = e.search_tsv.op("@@")(tsq)
        ent_hit = exists().where(
            event_entities.c.event_id == e.id,
            event_entities.c.entity_id.in_(f.q_entity_ids or [None]),
        )
        score = (func.ts_rank_cd(e.search_tsv, tsq) + 0.5 * ent_hit.cast(Integer)).label("score")
        q = q.add_columns(score).where(or_(fts, ent_hit))
        key = (score, e.last_article_at, e.id)
    elif sort == "rank":
        key = (e.relevance_rank, e.last_article_at, e.id)
    else:
        key = (e.last_article_at, e.id)
    if after:
        q = q.where(tuple_(*key) < tuple_(*(literal(v) for v in after)))
    q = q.order_by(*(k.desc() for k in key)).limit(limit)
    return [dict(r._mapping) for r in await session.execute(q)]


async def detail(session: AsyncSession, event_id: uuid.UUID) -> dict[str, Any] | None:
    row = (await session.execute(select(events).where(e.id == event_id))).first()
    if row is None:
        return None
    out = dict(row._mapping)
    links = await session.execute(
        select(event_articles).where(event_articles.c.event_id == event_id)
    )
    out["links"] = [dict(r._mapping) for r in links]
    ents = await session.execute(
        select(event_entities)
        .where(event_entities.c.event_id == event_id)
        .order_by(event_entities.c.mentions.desc())
    )
    out["entity_rows"] = [dict(r._mapping) for r in ents]
    return out


async def related(session: AsyncSession, event_id: uuid.UUID) -> list[dict[str, Any]]:
    q = (
        select(e.id, e.title, event_relations.c.kind, e.relevance, e.status, e.last_article_at)
        .join(event_relations, event_relations.c.related_event_id == e.id)
        .where(event_relations.c.event_id == event_id)
        .order_by(event_relations.c.score.desc().nulls_last(), e.last_article_at.desc())
    )
    return [dict(r._mapping) for r in await session.execute(q)]


async def autodraft_candidates(
    session: AsyncSession, min_rank: int, since: datetime, limit: int
) -> list[dict[str, Any]]:
    """NEW|REVIEWING, rank ≥ порога, свежие (BE-T3.15). basis_hash — sha256 состава и ключевых полей."""
    rows = await session.execute(
        text(
            "SELECT e.id, e.status, EXISTS (SELECT 1 FROM events.event_articles x WHERE x.event_id = e.id) AS has_articles,"
            " encode(sha256(convert_to(coalesce((SELECT string_agg(ea.article_id::text, ',' ORDER BY ea.article_id)"
            "   FROM events.event_articles ea WHERE ea.event_id = e.id), '') || '|' || e.title || '|' ||"
            "   coalesce(e.sport_id, '') || '|' || coalesce(e.competition_id::text, ''), 'UTF8')), 'hex') AS basis_hash"
            " FROM events.events e WHERE e.status IN ('NEW', 'REVIEWING') AND e.relevance_rank >= :r AND e.last_article_at >= :since"
            " ORDER BY e.relevance_rank DESC, e.last_article_at DESC LIMIT :k"
        ),
        {"r": min_rank, "since": since, "k": limit},
    )
    return [dict(r._mapping) for r in rows]


async def brief_candidates(
    session: AsyncSession, min_rank: int, since: datetime, limit: int
) -> list[dict[str, Any]]:
    """Свежие события выше порога (кроме отклонённых); article_hash — состав статей (пересборка брифа)."""
    rows = await session.execute(
        text(
            "SELECT e.id, encode(sha256(convert_to(coalesce((SELECT string_agg(ea.article_id::text, ','"
            "   ORDER BY ea.article_id) FROM events.event_articles ea WHERE ea.event_id = e.id), ''), 'UTF8')), 'hex')"
            "   AS article_hash"
            " FROM events.events e WHERE e.status <> 'REJECTED' AND e.relevance_rank >= :r"
            " AND e.last_article_at >= :since AND EXISTS (SELECT 1 FROM events.event_articles x WHERE x.event_id = e.id)"
            " ORDER BY e.relevance_rank DESC, e.last_article_at DESC LIMIT :k"
        ),
        {"r": min_rank, "since": since, "k": limit},
    )
    return [dict(r._mapping) for r in rows]


async def publish_candidates(
    session: AsyncSession,
    statuses: list[str],
    min_rank: int,
    since: datetime,
    limit: int,
    include: list[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    """Свежие события для каналов: грубый отбор в SQL, точные фильтры канала — в editorial."""
    q = (
        select(
            e.id,
            e.status,
            e.relevance,
            e.reliability,
            e.region,
            e.sport_id,
            e.source_ids,
            e.title,
            e.title_i18n,
            e.last_article_at,
        )
        .where(
            e.status.in_(statuses),
            e.relevance_rank >= min_rank,
            # закреплённые на время — даже если старше окна свежести
            or_(e.last_article_at >= since, e.id.in_(include or [])),
        )
        .order_by(e.relevance_rank.desc(), e.last_article_at.desc())
        .limit(limit)
    )
    return [dict(r._mapping) for r in await session.execute(q)]


async def article_ids(
    session: AsyncSession, event_id: uuid.UUID, unique_only: bool = False
) -> list[uuid.UUID]:
    rows = await session.execute(
        text(
            "SELECT article_id FROM events.event_articles WHERE event_id = :i"
            " AND NOT (is_duplicate AND :u)"
        ),
        {"i": event_id, "u": unique_only},
    )
    return [r[0] for r in rows]


async def set_title_translation(
    session: AsyncSession, event_id: uuid.UUID, lang: str, title: str
) -> None:
    await session.execute(
        text(
            "UPDATE events.events SET title_i18n = title_i18n || jsonb_build_object(CAST(:l AS text), CAST(:t AS text))"
            " WHERE id = :i"
        ),
        {"i": event_id, "l": lang, "t": title},
    )


async def translation_candidates(
    session: AsyncSession,
    lang: str,
    since: datetime,
    limit: int,
    event_id: uuid.UUID | None = None,
    min_rank: int = 2,
) -> list[dict[str, Any]]:
    """События без перевода заголовка или с устаревшим переводом сводки (хеш не совпал).
    Заголовок переводится у всех свежих событий; сводка — от важности min_rank (full) и у события,
    открытого редактором (:id)."""
    rows = await session.execute(
        text(
            "SELECT e.id, e.title, e.summary,"
            " (e.id IS NOT DISTINCT FROM CAST(:id AS uuid) OR e.relevance_rank >= :r) AS full"
            " FROM events.events e"
            " WHERE (e.id = :id OR CAST(:id AS uuid) IS NULL AND e.status <> 'REJECTED'"
            "  AND e.last_article_at >= :since)"
            " AND (e.title_i18n->>:l IS NULL"
            "  OR ((e.id IS NOT DISTINCT FROM CAST(:id AS uuid) OR e.relevance_rank >= :r)"
            "   AND e.summary IS NOT NULL"
            "   AND coalesce(e.summary_i18n->:l->>'h', '')"
            "      <> encode(sha256(convert_to(e.summary, 'UTF8')), 'hex')))"
            " ORDER BY e.relevance_rank DESC, e.last_article_at DESC LIMIT :k"
        ),
        {"l": lang, "since": since, "k": limit, "id": event_id, "r": min_rank},
    )
    return [dict(r._mapping) for r in rows]


async def set_translation(
    session: AsyncSession,
    event_id: uuid.UUID,
    lang: str,
    title: str,
    summary: tuple[str, str] | None,
) -> None:
    """summary — (sha256 исходной сводки, перевод)."""
    await session.execute(
        text(
            "UPDATE events.events SET title_i18n = title_i18n || jsonb_build_object(CAST(:l AS text), CAST(:t AS text)),"
            " summary_i18n = CASE WHEN CAST(:h AS text) IS NULL THEN summary_i18n ELSE summary_i18n"
            "  || jsonb_build_object(CAST(:l AS text), jsonb_build_object('h', CAST(:h AS text), 't', CAST(:s AS text))) END"
            " WHERE id = :i"
        ),
        {"i": event_id, "l": lang, "t": title, "h": summary[0] if summary else None,
         "s": summary[1] if summary else None},
    )  # fmt: skip


async def feed_page(
    session: AsyncSession,
    tab: str,
    f: EventFilters,
    min_rank: int,
    after: tuple[Any, ...] | None,
    limit: int,
    since: datetime | None = None,
    only_ids: list[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    """Лента с теми же фильтрами, что список событий; статус и окно — свои у вкладки.
    only_ids — только эти события (например, с постом на языке канала)."""
    q: Select[Any] = select(*LIST_COLS, e.status_changed_at, e.summary, e.summary_i18n)
    q = q.where(*_where(replace(f, status=[], from_=None, to=None, updated_since=None)))
    if tab == "suggested":
        # всё, что ещё можно отправить: от новых до черновиков; свежее окна автопостинга
        q = q.where(
            e.status.in_(["NEW", "REVIEWING", "SELECTED", "DRAFT"]),
            e.relevance_rank >= min_rank,
        )
        if since is not None:
            q = q.where(e.last_article_at >= since)
        key: tuple[ColumnElement[Any], ...] = (e.relevance_rank, e.last_article_at, e.id)
    else:
        q = q.where(e.status.in_(["READY", "PUBLISHED"]))
        key = (e.status_changed_at, e.id)
    if only_ids is not None:
        q = q.where(e.id.in_(only_ids))
    if after:
        q = q.where(tuple_(*key) < tuple_(*(literal(v) for v in after)))
    q = q.order_by(*(k.desc() for k in key)).limit(limit)
    return [dict(r._mapping) for r in await session.execute(q)]
