"""compute_state — чистая агрегация состояния события (BE-T2.17). Входы — DTO фасадов, как Any."""

import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sportintel.modules.events.domain.event import ComputedState
from sportintel.modules.events.domain.policies.clustering import incremental_centroid
from sportintel.modules.events.domain.policies.relevance import ArticleRelevance, compute_relevance
from sportintel.modules.events.domain.policies.reliability import (
    SourceEvidence,
    compute_reliability,
)
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AssessmentOrigin,
    Relevance,
    TextOrigin,
)

SEARCH_DOC_MAX, TOP_ENTITIES = 20_000, 30
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class RefreshInputs:
    links: list[ArticleLink]
    articles: dict[uuid.UUID, Any]  # ingestion.ArticleMeta
    enrichments: dict[uuid.UUID, Any]  # intelligence.EnrichmentDTO
    sources: dict[uuid.UUID, Any]  # sources.SourceMeta
    entities: dict[uuid.UUID, Any]  # taxonomy.EntityDTO
    open_key_conflicts: int = 0
    stale: bool = False
    language: str = "pt-BR"
    lead_max_chars: int = 500
    extractive: bool = True  # ai_routing.event_summary == "rules" (ADR-004)


def trim_sentences(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    out = ""
    for s in _SENTENCE.split(text):
        if len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    return out or text[: limit - 1].rstrip() + "…"


def _majority(values: list[Any]) -> Any:
    """Самое частое не-null; ничья — значение самой ранней статьи (values упорядочены по времени)."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    counts = Counter(present)
    top = max(counts.values())
    return next(v for v in present if counts[v] == top)


def _when(a: Any) -> datetime:
    return a.published_at or a.discovered_at  # type: ignore[no-any-return]


def main_article(primary: list[Any], sources: dict[uuid.UUID, Any]) -> Any:
    """OFFICIAL → самая ранняя tier A → самая ранняя (ADR-004)."""
    tier = {a.id: getattr(sources.get(a.source_id), "tier", None) for a in primary}
    for want in ("OFFICIAL", "A"):
        hits = [a for a in primary if tier[a.id] == want]
        if hits:
            return min(hits, key=_when)
    return min(primary, key=_when)


def compute_state(i: RefreshInputs) -> ComputedState:
    primary_ids = [
        lk.article_id for lk in i.links if not lk.is_duplicate and lk.article_id in i.articles
    ]
    primary = sorted((i.articles[a] for a in primary_ids), key=_when)
    all_arts = [i.articles[lk.article_id] for lk in i.links if lk.article_id in i.articles]
    enr: dict[uuid.UUID, Any] = {a.id: i.enrichments.get(a.id) for a in primary}

    sport = _majority([e.sport_id if e else None for e in enr.values()])
    region = _majority([getattr(i.sources.get(a.source_id), "region", None) for a in primary])
    competition = _majority([e.competition_id if e else None for e in enr.values()])
    mentions: Counter[uuid.UUID] = Counter()
    for e in enr.values():
        for row in e.entities if e else []:
            mentions[row["entity_id"]] += 1
    ents = [
        (eid, str(i.entities[eid].kind)) for eid, _ in mentions.most_common() if eid in i.entities
    ][:TOP_ENTITIES]

    evidence = [
        SourceEvidence(
            lk.article_id,
            i.articles[lk.article_id].source_id,
            getattr(i.sources.get(i.articles[lk.article_id].source_id), "tier", None),
            getattr(i.sources.get(i.articles[lk.article_id].source_id), "owner_group", None),
            lk.is_duplicate,
            bool(e and e.rumor_markers),
            bool(e and e.clickbait),
        )
        for lk in i.links
        if lk.article_id in i.articles
        for e in [i.enrichments.get(lk.article_id)]
    ]
    reliability = compute_reliability(evidence, i.open_key_conflicts)

    def prio(kind: str) -> int | None:
        ps = [i.entities[eid].priority for eid, k in ents if k == kind]
        return max(ps) if ps else None

    comp_priority = (
        i.entities[competition].priority if competition in i.entities else prio("competition")
    )
    rules_mode = any(e and e.method == "rules" for e in enr.values())
    relevance = compute_relevance(
        [
            ArticleRelevance(
                a.id, Relevance(enr[a.id].relevance), enr[a.id].relevance_rationale, _when(a), False
            )
            for a in primary
            if enr[a.id]
        ],
        comp_priority,
        prio("team"),
        i.stale,
        i.language,
        priorities_in_articles=rules_mode,
        base_origin=AssessmentOrigin.RULE if rules_mode else AssessmentOrigin.AI,
    )

    centroid, n = None, 0
    for e in enr.values():
        if e and e.embedding is not None:
            centroid, n = incremental_centroid(centroid, n, e.embedding), n + 1

    groups = {  # независимые = разные медиагруппы; недоверенные источники не считаются
        (i.sources[a.source_id].owner_group if a.source_id in i.sources else None)
        or f"src:{a.source_id}"
        for a in primary
        if getattr(i.sources.get(a.source_id), "tier", None) != "UNTRUSTED"
    }
    title = summary = None
    if i.extractive and primary:
        m = main_article(primary, i.sources)
        title, summary = m.title, trim_sentences(m.lead, i.lead_max_chars) if m.lead else None
    names = [i.entities[eid].name for eid, _ in ents]
    src_names = sorted({i.sources[a.source_id].name for a in all_arts if a.source_id in i.sources})
    doc = "\n".join(
        [
            title or "",
            summary or "",
            " ".join(names),
            " ".join(src_names),
            *[a.title for a in all_arts[:20]],
        ]
    )
    return ComputedState(
        title=title,
        title_origin=TextOrigin.SOURCE if title else None,
        summary=summary,
        summary_origin=TextOrigin.SOURCE if summary else None,
        sport_id=sport,
        region=region,
        competition_id=competition,
        entities=ents,
        entity_mentions={eid: mentions[eid] for eid, _ in ents},
        relevance=relevance,
        reliability=reliability,
        article_count=len(i.links),
        source_count=len({a.source_id for a in primary}),
        independent_source_count=len(groups),
        source_ids=sorted({a.source_id for a in all_arts}),
        centroid=centroid,
        search_doc=doc[:SEARCH_DOC_MAX],
        last_article_at=max((a.discovered_at for a in all_arts), default=None),
        occurred_at=_when(primary[0]) if primary else None,
        has_clickbait=any(e and e.clickbait for e in enr.values()),
        stale_suspected=i.stale,
    )
