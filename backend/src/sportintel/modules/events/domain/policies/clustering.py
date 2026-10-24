"""Скоринг кандидатов кластеризации (BE-T2.14; лексический режим — ADR-004)."""

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sportintel.modules.events.domain.values import EventStatus


@dataclass(frozen=True)
class ArticleFeatures:
    embedding: list[float] | None
    entity_ids: frozenset[uuid.UUID]
    competition_id: uuid.UUID | None
    sport_id: str | None


@dataclass(frozen=True)
class CandidateRow:
    event_id: uuid.UUID
    cosine: float | None
    competition_id: uuid.UUID | None
    entity_ids: frozenset[uuid.UUID]
    status: EventStatus
    lex: float = 0.0


def jaccard(a: frozenset[uuid.UUID], b: frozenset[uuid.UUID]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def score(article: ArticleFeatures, cand: CandidateRow, claim_conflict: bool, p: Any) -> float:
    jac = jaccard(article.entity_ids, cand.entity_ids)
    same = 1.0 if article.competition_id and article.competition_id == cand.competition_id else 0.0
    if article.embedding is None:
        s = (p.w_lex * cand.lex + p.w_entities * jac + p.w_competition * same) / (
            p.w_lex + p.w_entities + p.w_competition
        )
    else:
        s = p.w_cos * (cand.cosine or 0.0) + p.w_entities * jac + p.w_competition * same
    return float(s - (p.claim_conflict_penalty if claim_conflict else 0.0))


def decide(best: float | None, p: Any) -> Literal["attach", "gray", "new"]:
    if best is None or best <= p.t_low:
        return "new"
    return "attach" if best >= p.t_high else "gray"


def incremental_centroid(c: list[float] | None, n: int, e: list[float]) -> list[float]:
    """c' = normalize((c·n + e)/(n+1)); n — статьи с эмбеддингом до прикрепления (BE-T2.15 §7)."""
    if c is None or n <= 0:
        v = list(e)
    else:
        v = [(ci * n + ei) / (n + 1) for ci, ei in zip(c, e, strict=True)]
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v] if norm else v
