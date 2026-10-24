import uuid
from collections.abc import Collection
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.events.domain.event import Event
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AssessmentOrigin,
    AttachMethod,
    EventOrigin,
    EventStatus,
    OverrideField,
    RejectionReason,
    RelationKind,
    Relevance,
    RelevanceAssessment,
    Reliability,
    ReliabilityAssessment,
    ReliabilityFactor,
    ReliabilityFactorItem,
    TextOrigin,
)
from sportintel.modules.events.infrastructure.tables import (
    event_articles,
    event_entities,
    event_relations,
    events,
)
from sportintel.platform.errors import ConcurrencyConflict


def _row(e: Event) -> dict[str, Any]:
    return {
        "id": e.id,
        "title": e.title,
        "title_origin": e.title_origin.value,
        "summary": e.summary,
        "summary_origin": e.summary_origin.value if e.summary_origin else None,
        "occurred_at": e.occurred_at,
        "first_seen_at": e.first_seen_at,
        "last_article_at": e.last_article_at,
        "sport_id": e.sport_id,
        "region": e.region,
        "competition_id": e.competition_id,
        "relevance": e.relevance.level.value,
        "relevance_rationale": e.relevance.rationale,
        "relevance_origin": e.relevance.origin.value,
        "relevance_reason": e.relevance.reason,
        "reliability": e.reliability.level.value,
        "reliability_factors": [
            {"code": f.code.value, "detail": f.detail} for f in e.reliability.factors
        ],
        "reliability_origin": e.reliability.origin.value,
        "reliability_reason": e.reliability.reason,
        "status": e.status.value,
        "status_changed_at": e.status_changed_at or e.first_seen_at,
        "rejection_reason": e.rejection_reason.value if e.rejection_reason else None,
        "rejection_comment": e.rejection_comment,
        "assignee_id": e.assignee_id,
        "manual_overrides": sorted(f.value for f in e.manual_overrides),
        "has_updates_since_edit": e.has_updates_since_edit,
        "has_open_conflicts": e.has_open_conflicts,
        "stale_suspected": e.stale_suspected,
        "has_clickbait": e.has_clickbait,
        "article_count": e.article_count,
        "source_count": e.source_count,
        "independent_source_count": e.independent_source_count,
        "centroid": e.centroid,
        "source_ids": e.source_ids,
        "origin": e.origin.value,
        "created_by": e.created_by,
        "refresh_requested_at": e.refresh_requested_at,
        "search_doc": e.search_doc,
        "version": e.version,
        "draft_state": e.draft_state,
        "draft_last_human_author_id": e.draft_last_human_author_id,
    }


def event_from_row(
    m: dict[str, Any], links: list[ArticleLink], entities: list[tuple[uuid.UUID, str]]
) -> Event:
    return Event(
        id=m["id"],
        title=m["title"],
        title_origin=TextOrigin(m["title_origin"]),
        occurred_at=m["occurred_at"],
        first_seen_at=m["first_seen_at"],
        last_article_at=m["last_article_at"],
        status=EventStatus(m["status"]),
        status_changed_at=m["status_changed_at"],
        summary=m["summary"],
        summary_origin=TextOrigin(m["summary_origin"]) if m["summary_origin"] else None,
        sport_id=m["sport_id"],
        region=m["region"],
        competition_id=m["competition_id"],
        relevance=RelevanceAssessment(
            Relevance(m["relevance"]),
            m["relevance_rationale"],
            AssessmentOrigin(m["relevance_origin"]),
            m["relevance_reason"],
        ),
        reliability=ReliabilityAssessment(
            Reliability(m["reliability"]),
            tuple(
                ReliabilityFactorItem(ReliabilityFactor(f["code"]), f.get("detail", ""))
                for f in m["reliability_factors"]
            ),
            AssessmentOrigin(m["reliability_origin"]),
            m["reliability_reason"],
        ),
        rejection_reason=RejectionReason(m["rejection_reason"]) if m["rejection_reason"] else None,
        rejection_comment=m["rejection_comment"],
        assignee_id=m["assignee_id"],
        manual_overrides={OverrideField(f) for f in m["manual_overrides"]},
        has_updates_since_edit=m["has_updates_since_edit"],
        has_open_conflicts=m["has_open_conflicts"],
        stale_suspected=m["stale_suspected"],
        has_clickbait=m["has_clickbait"],
        article_count=m["article_count"],
        source_count=m["source_count"],
        independent_source_count=m["independent_source_count"],
        centroid=[float(x) for x in m["centroid"]] if m["centroid"] is not None else None,
        source_ids=list(m["source_ids"]),
        entities=entities,
        origin=EventOrigin(m["origin"]),
        created_by=m["created_by"],
        refresh_requested_at=m["refresh_requested_at"],
        search_doc=m["search_doc"],
        version=m["version"],
        links=links,
        draft_state=m["draft_state"],
        draft_last_human_author_id=m["draft_last_human_author_id"],
    )


class SqlEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, event_id: uuid.UUID, *, for_update: bool = False) -> Event | None:
        q = select(events).where(events.c.id == event_id)
        if for_update:
            q = q.with_for_update()
        row = (await self.session.execute(q)).first()
        if row is None:
            return None
        links = [
            ArticleLink(
                r.article_id,
                r.attached_at,
                r.attach_score,
                AttachMethod(r.attach_method),
                r.cluster_locked,
                r.is_duplicate,
            )
            for r in await self.session.execute(
                select(event_articles)
                .where(event_articles.c.event_id == event_id)
                .order_by(event_articles.c.attached_at)
            )
        ]
        ents = [
            (r.entity_id, r.role)
            for r in await self.session.execute(
                select(event_entities).where(event_entities.c.event_id == event_id)
            )
        ]
        return event_from_row(dict(row._mapping), links, ents)

    async def add(self, e: Event) -> None:
        await self.session.execute(pg_insert(events).values(**_row(e)))
        await self._insert_links(e.id, e.links)

    async def _insert_links(self, event_id: uuid.UUID, links: list[ArticleLink]) -> None:
        if links:
            await self.session.execute(
                pg_insert(event_articles).values(
                    [
                        {
                            "article_id": lk.article_id,
                            "event_id": event_id,
                            "attached_at": lk.attached_at,
                            "attach_score": lk.score,
                            "attach_method": lk.method.value,
                            "cluster_locked": lk.cluster_locked,
                            "is_duplicate": lk.is_duplicate,
                        }
                        for lk in links
                    ]
                )
            )

    async def save(self, e: Event, expected_version: int) -> None:
        values = _row(e)
        values.pop("id")
        values["version"] = expected_version + 1
        res = await self.session.execute(
            update(events)
            .where(events.c.id == e.id, events.c.version == expected_version)
            .values(**values)
            .returning(events.c.id)
        )
        if res.first() is None:
            raise ConcurrencyConflict(current=None)
        current = {
            r.article_id
            for r in await self.session.execute(
                select(event_articles.c.article_id).where(event_articles.c.event_id == e.id)
            )
        }
        wanted = {lk.article_id for lk in e.links}
        if current - wanted:
            await self.session.execute(
                delete(event_articles).where(event_articles.c.article_id.in_(current - wanted))
            )
        await self._insert_links(e.id, [lk for lk in e.links if lk.article_id not in current])
        e.version = expected_version + 1

    async def event_id_for_article(self, article_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await self.session.execute(
                select(event_articles.c.event_id).where(event_articles.c.article_id == article_id)
            )
        ).scalar()

    async def event_ids_for_articles(
        self, ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, uuid.UUID]:
        if not ids:
            return {}
        rows = await self.session.execute(
            select(event_articles.c.article_id, event_articles.c.event_id).where(
                event_articles.c.article_id.in_(list(ids))
            )
        )
        return {a: e for a, e in rows}

    async def replace_entities(
        self, event_id: uuid.UUID, rows: list[tuple[uuid.UUID, str, int, bool]]
    ) -> None:
        await self.session.execute(
            delete(event_entities).where(event_entities.c.event_id == event_id)
        )
        if rows:
            await self.session.execute(
                pg_insert(event_entities).values(
                    [
                        {
                            "event_id": event_id,
                            "entity_id": i,
                            "role": r,
                            "mentions": n,
                            "manual": m,
                        }
                        for i, r, n, m in rows
                    ]
                )
            )

    async def replace_relations(
        self, event_id: uuid.UUID, kind: RelationKind, rows: list[tuple[uuid.UUID, float | None]]
    ) -> None:
        await self.session.execute(
            delete(event_relations).where(
                event_relations.c.event_id == event_id, event_relations.c.kind == kind.value
            )
        )
        if rows:
            await self.session.execute(
                pg_insert(event_relations)
                .values(
                    [
                        {
                            "event_id": event_id,
                            "related_event_id": r,
                            "kind": kind.value,
                            "score": s,
                        }
                        for r, s in rows
                        if r != event_id
                    ]
                )
                .on_conflict_do_nothing()
            )

    async def clear_refresh(self, event_id: uuid.UUID) -> None:
        """Пустой diff: снять запрос пересчёта без увеличения version (BE-T2.17 §12)."""
        await self.session.execute(
            update(events).where(events.c.id == event_id).values(refresh_requested_at=None)
        )

    async def related_by_entities(
        self, event_id: uuid.UUID, around: datetime, hours: int = 72, limit: int = 5
    ) -> list[tuple[uuid.UUID, float | None]]:
        rows = await self.session.execute(
            text(
                "SELECT o.event_id, count(*) AS shared FROM events.event_entities me"
                " JOIN events.event_entities o ON o.entity_id = me.entity_id AND o.event_id <> me.event_id"
                " JOIN events.events e ON e.id = o.event_id"
                " WHERE me.event_id = :id AND e.occurred_at BETWEEN :lo AND :hi"
                " GROUP BY o.event_id HAVING count(*) >= 2 ORDER BY shared DESC, o.event_id LIMIT :k"
            ),
            {
                "id": event_id,
                "lo": around - timedelta(hours=hours),
                "hi": around + timedelta(hours=hours),
                "k": limit,
            },
        )
        return [(i, float(n)) for i, n in rows]

    async def due_refresh(self, before: datetime, limit: int = 500) -> list[uuid.UUID]:
        rows = await self.session.execute(
            select(events.c.id)
            .where(events.c.refresh_requested_at < before)
            .order_by(events.c.refresh_requested_at)
            .limit(limit)
        )
        return [r[0] for r in rows]

    async def set_summary_citations(self, event_id: uuid.UUID, keep: set[int]) -> None:
        """Человеческий summary: цитаты только для оставшихся [n], grounding сбрасывается (BE-T3.4)."""
        await self.session.execute(
            text(
                "UPDATE events.events SET summary_grounding = NULL, summary_citations = coalesce((SELECT jsonb_agg(c)"
                " FROM jsonb_array_elements(summary_citations) c WHERE (c->>'n')::int = ANY(:keep)), '[]'::jsonb) WHERE id = :id"
            ),
            {"id": event_id, "keep": list(keep)},
        )

    async def similar_old(
        self,
        event_id: uuid.UUID,
        centroid: list[float] | None,
        title: str,
        before: datetime,
        days: int,
        window_hours: int,
        min_similarity: float,
    ) -> list[tuple[uuid.UUID, float | None]]:
        """Похожие события до окна кластеризации (BE-T4.6): по centroid, а без эмбеддингов — по заголовку (ADR-004)."""
        lo, hi = before - timedelta(days=days), before - timedelta(hours=window_hours)
        params: dict[str, Any] = {"id": event_id, "lo": lo, "hi": hi, "m": min_similarity}
        if centroid is not None:
            sql = (
                "SELECT id, 1 - (centroid <=> CAST(:c AS vector)) AS s FROM events.events WHERE id <> :id"
                " AND centroid IS NOT NULL AND last_article_at >= :lo AND last_article_at < :hi"
                " AND 1 - (centroid <=> CAST(:c AS vector)) >= :m ORDER BY s DESC LIMIT 3"
            )
            params["c"] = str(centroid)
        else:
            sql = (
                "SELECT id, similarity(platform.immutable_unaccent(lower(title)), platform.immutable_unaccent(lower(:t))) AS s"
                " FROM events.events WHERE id <> :id AND last_article_at >= :lo AND last_article_at < :hi"
                " AND similarity(platform.immutable_unaccent(lower(title)), platform.immutable_unaccent(lower(:t))) >= :m"
                " ORDER BY s DESC LIMIT 3"
            )
            params["t"] = title
        return [(i, float(s)) for i, s in await self.session.execute(text(sql), params)]

    async def request_refresh(self, ids: Collection[uuid.UUID], now: datetime) -> None:
        if ids:
            await self.session.execute(
                update(events).where(events.c.id.in_(list(ids))).values(refresh_requested_at=now)
            )
