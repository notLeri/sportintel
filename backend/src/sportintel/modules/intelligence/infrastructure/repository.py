import json
import uuid
from collections.abc import Collection
from dataclasses import asdict
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.intelligence.domain.enrich_output import EnrichOutput
from sportintel.modules.intelligence.infrastructure.tables import (
    article_enrichments,
    article_entities,
)


class SqlEnrichmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(
        self,
        article_id: uuid.UUID,
        out: EnrichOutput,
        prompt_version: str,
        now: datetime,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "article_id": article_id,
            "language": out.language,
            "sport_id": out.sport,
            "competition_id": out.competition.entity_id if out.competition else None,
            "relevance": out.relevance.level.value,
            "relevance_rationale": out.relevance.rationale,
            "clickbait": out.clickbait,
            "rumor_markers": out.rumor_markers,
            "event_date_hint": out.event_date_hint,
            "claims": [
                {**asdict(c), "attribute": c.attribute.value, "modality": c.modality.value}
                for c in out.claims
            ],
            "raw_entities": [
                {**asdict(e), "entity_id": str(e.entity_id) if e.entity_id else None}
                for e in out.entities
            ],
            "headline": out.headline_neutral,
            "embedding": embedding,
            "embedding_model": embedding_model,
            "method": out.method,
            "prompt_version": prompt_version,
            "enriched_at": now,
            "copied_from": None,
        }
        stmt = pg_insert(article_enrichments).values(**values)
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["article_id"],
                set_={k: stmt.excluded[k] for k in values if k != "article_id"},
            )
        )
        await self.session.execute(
            delete(article_entities).where(article_entities.c.article_id == article_id)
        )
        counts: dict[uuid.UUID, tuple[str, int]] = {}
        for e in out.entities:
            if e.entity_id:
                role, n = counts.get(e.entity_id, (e.role, 0))
                counts[e.entity_id] = (
                    "subject" if "subject" in (role, e.role) else "mentioned",
                    n + 1,
                )
        if out.competition and out.competition.entity_id:
            counts.setdefault(out.competition.entity_id, ("mentioned", 1))
        if counts:
            await self.session.execute(
                pg_insert(article_entities).values(
                    [
                        {"article_id": article_id, "entity_id": k, "role": r, "mentions": n}
                        for k, (r, n) in counts.items()
                    ]
                )
            )

    async def copy_from(self, article_id: uuid.UUID, original_id: uuid.UUID, now: datetime) -> bool:
        """Синдицированная копия получает обогащение оригинала (BE-T2.8 шаг 2)."""
        res = await self.session.execute(
            text(
                "INSERT INTO intelligence.article_enrichments (article_id, language, sport_id, competition_id, relevance,"
                " relevance_rationale, clickbait, rumor_markers, event_date_hint, claims, raw_entities, headline, embedding,"
                " embedding_model, method, prompt_version, ai_run_id, copied_from, enriched_at)"
                " SELECT :a, language, sport_id, competition_id, relevance, relevance_rationale, clickbait, rumor_markers,"
                " event_date_hint, claims, raw_entities, headline, embedding, embedding_model, method, prompt_version, ai_run_id, :o, :now"
                " FROM intelligence.article_enrichments WHERE article_id = :o"
                " ON CONFLICT (article_id) DO NOTHING"
            ),
            {"a": article_id, "o": original_id, "now": now},
        )
        if not res.rowcount:  # type: ignore[attr-defined]
            exists = (
                await self.session.execute(
                    select(article_enrichments.c.article_id).where(
                        article_enrichments.c.article_id == original_id
                    )
                )
            ).first()
            if exists is None:
                return False
        await self.session.execute(
            text(
                "INSERT INTO intelligence.article_entities (article_id, entity_id, role, mentions)"
                " SELECT :a, entity_id, role, mentions FROM intelligence.article_entities WHERE article_id = :o ON CONFLICT DO NOTHING"
            ),
            {"a": article_id, "o": original_id},
        )
        return True

    async def get_many(self, ids: Collection[uuid.UUID]) -> list[dict[str, Any]]:
        if not ids:
            return []
        rows = await self.session.execute(
            select(article_enrichments).where(article_enrichments.c.article_id.in_(list(ids)))
        )
        out = [dict(r._mapping) for r in rows]
        ents = await self.session.execute(
            select(article_entities).where(article_entities.c.article_id.in_(list(ids)))
        )
        by_article: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for e in ents:
            by_article.setdefault(e.article_id, []).append(dict(e._mapping))
        for row in out:
            row["entities"] = by_article.get(row["article_id"], [])
            if isinstance(row["claims"], str):
                row["claims"] = json.loads(row["claims"])
        return out

    async def relink_batch(
        self,
        mention_norm: str,
        entity_id: uuid.UUID,
        since: datetime,
        after: uuid.UUID | None,
        limit: int,
    ) -> tuple[list[uuid.UUID], uuid.UUID | None]:
        """Пачка перепривязки (BE-T4.9): статьи с упоминанием mention_norm в raw_entities → article_entities.
        → (перепривязанные статьи, последний просмотренный id или None, если пачек больше нет)."""
        from sportintel.platform.text import normalize_name

        rows = (
            await self.session.execute(
                text(
                    "SELECT article_id, raw_entities FROM intelligence.article_enrichments"
                    " WHERE enriched_at >= :since AND (CAST(:after AS uuid) IS NULL OR article_id > :after)"
                    " AND platform.immutable_unaccent(lower(raw_entities::text)) LIKE :pat ORDER BY article_id LIMIT :k"
                ),
                {"since": since, "after": after, "pat": f"%{mention_norm}%", "k": limit},
            )
        ).all()
        hit: list[uuid.UUID] = []
        for article_id, raw in rows:
            roles = [
                m.get("role", "mentioned")
                for m in (raw or [])
                if normalize_name(m.get("mention", "")) == mention_norm
            ]
            if roles:
                role = "subject" if "subject" in roles else "mentioned"
                await self.session.execute(
                    text(
                        "INSERT INTO intelligence.article_entities (article_id, entity_id, role, mentions) VALUES (:a, :e, :r, :n)"
                        " ON CONFLICT (article_id, entity_id) DO NOTHING"
                    ),
                    {"a": article_id, "e": entity_id, "r": role, "n": len(roles)},
                )
                hit.append(article_id)
        return hit, (rows[-1][0] if len(rows) == limit else None)
