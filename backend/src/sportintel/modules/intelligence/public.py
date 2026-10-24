"""Публичный фасад модуля intelligence."""

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sportintel.modules.intelligence.api.router import router
from sportintel.modules.intelligence.application import (
    rule_enrich as _seed_rules,  # noqa: F401 — регистрирует seed enrich_rules
)
from sportintel.modules.intelligence.infrastructure.repository import SqlEnrichmentRepository
from sportintel.platform.db import UnitOfWork

__all__ = ["EnrichmentDTO", "get_embeddings", "get_enrichment", "get_enrichments", "router"]


@dataclass(frozen=True)
class EnrichmentDTO:
    article_id: uuid.UUID
    language: str | None
    sport_id: str | None
    competition_id: uuid.UUID | None
    relevance: str
    relevance_rationale: str
    clickbait: bool
    rumor_markers: list[str]
    claims: list[dict[str, Any]]
    entities: list[dict[str, Any]] = field(default_factory=list)  # {entity_id, role, mentions}
    embedding: list[float] | None = None
    headline_neutral: str = ""
    method: str = "rules"
    event_date_hint: date | None = None


def _dto(r: dict[str, Any]) -> EnrichmentDTO:
    emb = r.get("embedding")
    return EnrichmentDTO(
        article_id=r["article_id"],
        language=r["language"],
        sport_id=r["sport_id"],
        competition_id=r["competition_id"],
        relevance=r["relevance"],
        relevance_rationale=r["relevance_rationale"],
        clickbait=r["clickbait"],
        rumor_markers=list(r["rumor_markers"]),
        claims=list(r["claims"]),
        entities=[
            {"entity_id": e["entity_id"], "role": e["role"], "mentions": e["mentions"]}
            for e in r["entities"]
        ],
        embedding=[float(x) for x in emb] if emb is not None else None,
        headline_neutral=r["headline"],
        method=r["method"],
        event_date_hint=r["event_date_hint"],
    )


async def get_enrichments(
    uow: UnitOfWork, ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, EnrichmentDTO]:
    return {
        r["article_id"]: _dto(r) for r in await SqlEnrichmentRepository(uow.session).get_many(ids)
    }


async def get_enrichment(uow: UnitOfWork, article_id: uuid.UUID) -> EnrichmentDTO | None:
    return (await get_enrichments(uow, [article_id])).get(article_id)


async def get_embeddings(
    uow: UnitOfWork, ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[float]]:
    return {
        k: v.embedding
        for k, v in (await get_enrichments(uow, ids)).items()
        if v.embedding is not None
    }
