"""build_evidence_pack (BE-T2.19): общий вход для шаблонного (BE-T3.9) и LM-черновика/summary."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sportintel.modules.events.domain.evidence import (
    ArticleEvidence,
    EvidenceFragment,
    select_fragments,
)
from sportintel.modules.events.domain.values import RelevanceAssessment, ReliabilityAssessment
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.intelligence import public as intelligence
from sportintel.modules.sources import public as sources
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import NotFound


@dataclass(frozen=True)
class PackSource:
    """Основные статьи в порядке «основной статьи»: OFFICIAL → tier A → остальные, внутри — по времени."""

    article_id: uuid.UUID
    source_name: str
    tier: str | None
    url: str
    lead: str | None
    title: str
    language: str | None = None  # язык статьи (или источника): шаблон пишет её текстом


@dataclass(frozen=True)
class EvidencePack:
    event_id: uuid.UUID
    title: str
    fragments: list[EvidenceFragment]
    claims: list[dict[str, Any]]
    reliability: ReliabilityAssessment
    relevance: RelevanceAssessment
    known_names: list[str]
    language: str = "pt-BR"
    sport_id: str | None = None
    open_conflicts: list[dict[str, Any]] = field(default_factory=list)  # BE-T4.1
    sources: list[PackSource] = field(default_factory=list)
    competition_name: str | None = None
    competition_name_i18n: dict[str, str] = field(default_factory=dict)  # для хэштегов поста
    team_names: list[str] = field(default_factory=list)
    has_open_conflicts: bool = False
    status: str = "NEW"
    occurred_at: datetime | None = None


async def build_evidence_pack(
    uow: UnitOfWork,
    event_id: uuid.UUID,
    max_fragments: int,
    clock: Clock,
    repo_for: Callable[[UnitOfWork], Any],
) -> EvidencePack:
    event = await repo_for(uow).get(event_id)
    if event is None:
        raise NotFound(f"event {event_id} not found")
    ids = [lk.article_id for lk in event.links if not lk.is_duplicate]
    metas = await ingestion.get_articles_meta(uow, ids)
    enr = await intelligence.get_enrichments(uow, ids)
    srcs = await sources.get_sources_meta(uow, {m.source_id for m in metas.values()})
    evidence = []
    langs: dict[uuid.UUID, str | None] = {}
    for aid, m in metas.items():
        # ponytail: текст по одной статье (get_text с TTL); пакетный запрос — если событий с 50+ статьями станет много.
        full = await ingestion.get_article_for_enrichment(uow, aid, clock)
        s = srcs.get(m.source_id)
        langs[aid] = full.language or (s.language if s else None)
        quotes = tuple(c["quote"] for c in (enr[aid].claims if aid in enr else []))
        evidence.append(
            ArticleEvidence(
                aid,
                s.name if s else "",
                s.tier if s else None,
                m.published_at or m.discovered_at,
                m.title,
                m.lead,
                full.text,
                quotes,
            )
        )
    ents = await taxonomy.get_entities(
        uow,
        [e for e, _ in event.entities] + ([event.competition_id] if event.competition_id else []),
    )
    order = {"OFFICIAL": 0, "A": 1}
    ranked = sorted(evidence, key=lambda a: (order.get(a.source_tier or "", 2), a.published_at))
    pack_sources = [
        PackSource(
            a.article_id,
            a.source_name,
            a.source_tier,
            metas[a.article_id].url,
            a.lead,
            a.title,
            langs.get(a.article_id),
        )
        for a in ranked
    ]
    comp = ents.get(event.competition_id) if event.competition_id else None
    return EvidencePack(
        event_id=event.id,
        title=event.title,
        fragments=select_fragments(evidence, max_fragments),
        claims=[c for e in enr.values() for c in e.claims],
        reliability=event.reliability,
        relevance=event.relevance,
        known_names=sorted(d.name for d in ents.values()),
        sport_id=event.sport_id,
        sources=pack_sources,
        competition_name=comp.name if comp else None,
        competition_name_i18n=dict(comp.name_i18n) if comp else {},
        team_names=[ents[i].name for i, r in event.entities if r == "team" and i in ents],
        has_open_conflicts=event.has_open_conflicts,
        status=event.status.value,
        occurred_at=event.occurred_at,
    )
