"""SQL кандидатов кластеризации (BE-T2.14): centroid (если есть) ∪ общие сущности ∪ похожий заголовок."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.events.domain.policies.clustering import CandidateRow
from sportintel.modules.events.domain.values import EventStatus
from sportintel.platform.text import normalize_name


async def find_candidates(
    session: AsyncSession,
    embedding: list[float] | None,
    entity_ids: set[uuid.UUID],
    sport_id: str | None,
    at: datetime,
    window_hours: int,
    top_k: int,
    *,
    title: str | None = None,
    lex_min: float = 0.2,
    region: str | None = None,
) -> list[CandidateRow]:
    since = at - timedelta(hours=window_hours)
    base = {"since": since, "sport": sport_id, "region": region, "k": top_k}
    found: dict[uuid.UUID, dict[str, float | None]] = {}
    emb = str(embedding) if embedding is not None else None
    if emb is not None:
        await session.execute(text("SET LOCAL hnsw.ef_search = 100"))
        rows = await session.execute(
            text(
                "SELECT id, 1 - (centroid <=> CAST(:emb AS vector)) FROM events.events"
                " WHERE centroid IS NOT NULL AND last_article_at >= :since AND (sport_id = :sport OR sport_id IS NULL OR CAST(:sport AS text) IS NULL) AND (region = :region OR region IS NULL OR CAST(:region AS text) IS NULL)"
                " ORDER BY centroid <=> CAST(:emb AS vector) LIMIT :k"
            ),
            {**base, "emb": emb},
        )
        for i, cos in rows:
            found[i] = {"cosine": float(cos)}
    if entity_ids:
        rows = await session.execute(
            text(
                "SELECT ee.event_id FROM events.event_entities ee JOIN events.events e ON e.id = ee.event_id"
                " WHERE ee.entity_id = ANY(:ents) AND e.last_article_at >= :since AND (sport_id = :sport OR sport_id IS NULL OR CAST(:sport AS text) IS NULL) AND (region = :region OR region IS NULL OR CAST(:region AS text) IS NULL)"
                " GROUP BY ee.event_id HAVING count(*) >= 2 LIMIT :k"
            ),
            {**base, "ents": list(entity_ids)},
        )
        for (i,) in rows:
            found.setdefault(i, {})
    if title and normalize_name(title):
        await session.execute(
            text("SELECT set_config('pg_trgm.similarity_threshold', :m, true)"), {"m": str(lex_min)}
        )
        rows = await session.execute(
            text(
                "SELECT id, similarity(platform.immutable_unaccent(lower(title)), :t) AS s FROM events.events"
                " WHERE platform.immutable_unaccent(lower(title)) % :t AND last_article_at >= :since AND (sport_id = :sport OR sport_id IS NULL OR CAST(:sport AS text) IS NULL) AND (region = :region OR region IS NULL OR CAST(:region AS text) IS NULL)"
                " ORDER BY s DESC LIMIT :k"
            ),
            {**base, "t": normalize_name(title)},
        )
        for i, s in rows:
            found.setdefault(i, {})["lex"] = float(s)
    if not found:
        return []
    ids = list(found)
    meta = await session.execute(
        text(
            "SELECT e.id, e.competition_id, e.status, 1 - (e.centroid <=> CAST(:emb AS vector)), similarity(platform.immutable_unaccent(lower(e.title)), :t),"
            " coalesce(array_agg(ee.entity_id) FILTER (WHERE ee.entity_id IS NOT NULL), '{}')"
            " FROM events.events e LEFT JOIN events.event_entities ee ON ee.event_id = e.id"
            " WHERE e.id = ANY(:ids) GROUP BY e.id"
        ),
        {"ids": ids, "emb": emb, "t": normalize_name(title or "")},
    )
    return [
        CandidateRow(
            i,
            float(cos) if cos is not None else None,
            comp,
            frozenset(ents),
            EventStatus(st),
            float(lex or 0.0),
        )
        for i, comp, st, cos, lex, ents in meta
    ]
