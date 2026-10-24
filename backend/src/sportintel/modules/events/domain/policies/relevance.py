"""Relevance события из relevance статей (BE-T2.13)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sportintel.modules.events.domain.values import (
    RELEVANCE_RANK,
    AssessmentOrigin,
    Relevance,
    RelevanceAssessment,
)

RATIONALE_MAX = 400
# Поправки — кодами, без языка: текст на языке интерфейса собирает интерфейс
MODIFIER = {
    "priority_up": " · priority_up",
    "priority_down": " · priority_down",
    "stale": " · stale",
}
BY_RANK = {v: k for k, v in RELEVANCE_RANK.items()}


@dataclass(frozen=True)
class ArticleRelevance:
    article_id: uuid.UUID
    level: Relevance
    rationale: str
    published_at: datetime
    is_duplicate: bool


def _shift(level: Relevance, delta: int) -> Relevance:
    return BY_RANK[min(3, max(1, RELEVANCE_RANK[level] + delta))]


def compute_relevance(
    items: list[ArticleRelevance],
    competition_priority: int | None,
    max_team_priority: int | None,
    stale: bool,
    language: str = "pt-BR",
    *,
    priorities_in_articles: bool = False,
    base_origin: AssessmentOrigin = AssessmentOrigin.AI,
) -> RelevanceAssessment:
    """priorities_in_articles: обогащение по правилам уже учло приоритет турнира/клуба (ADR-004) —
    повторный +1 не применяется, иначе почти любая новость Série A станет HIGH."""
    real = [i for i in items if not i.is_duplicate]
    if not real:
        return RelevanceAssessment(Relevance.LOW, "", AssessmentOrigin.RULE)
    base = max((i.level for i in real), key=lambda lv: RELEVANCE_RANK[lv])
    rationale = min((i for i in real if i.level == base), key=lambda i: i.published_at).rationale
    if base == Relevance.IRRELEVANT:
        return RelevanceAssessment(base, rationale[:RATIONALE_MAX], base_origin)
    texts = MODIFIER
    level: Relevance = base
    suffix = ""
    if (
        not priorities_in_articles
        and 2 in (competition_priority, max_team_priority)
        and base in {Relevance.LOW, Relevance.MEDIUM}
    ):
        level, suffix = _shift(level, +1), suffix + texts["priority_up"]
    if competition_priority == -1:
        level, suffix = _shift(level, -1), suffix + texts["priority_down"]
    if stale:
        level, suffix = _shift(level, -1), suffix + texts["stale"]
    origin = base_origin if not suffix else AssessmentOrigin.RULE
    return RelevanceAssessment(level, rationale[: RATIONALE_MAX - len(suffix)] + suffix, origin)
