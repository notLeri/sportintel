"""Детерминированная политика reliability (BE-T2.12)."""

import uuid
from dataclasses import dataclass

from sportintel.modules.events.domain.values import (
    AssessmentOrigin,
    Reliability,
    ReliabilityAssessment,
    ReliabilityFactorItem,
)
from sportintel.modules.events.domain.values import (
    ReliabilityFactor as F,
)

TIER_ORDER = {"OFFICIAL": 4, "A": 3, "B": 2, "C": 1, None: 0}
UNTRUSTED = "UNTRUSTED"
DOWN = {Reliability.HIGH: Reliability.MEDIUM, Reliability.MEDIUM: Reliability.LOW}


@dataclass(frozen=True)
class SourceEvidence:
    article_id: uuid.UUID
    source_id: uuid.UUID
    tier: str | None
    owner_group: str | None
    is_duplicate: bool
    has_rumor_markers: bool
    clickbait: bool

    @property
    def group(self) -> str:
        return self.owner_group or f"src:{self.source_id}"


def compute_reliability(
    evidence: list[SourceEvidence], open_key_conflicts: int
) -> ReliabilityAssessment:
    present = [e for e in evidence if not e.is_duplicate]
    # Недоверенные источники ничего не подтверждают: оцениваем по остальным.
    items = [e for e in present if e.tier != UNTRUSTED]
    factors: list[ReliabilityFactorItem] = []

    def done(level: Reliability) -> ReliabilityAssessment:
        return ReliabilityAssessment(level, tuple(factors), AssessmentOrigin.RULE)

    if not present:
        factors.append(ReliabilityFactorItem(F.NO_ARTICLES))
        return done(Reliability.UNKNOWN)
    if not items:
        factors.append(ReliabilityFactorItem(F.UNTRUSTED_ONLY))
        return done(Reliability.LOW)

    groups: dict[str, list[SourceEvidence]] = {}
    for e in items:
        groups.setdefault(e.group, []).append(e)
    best = {g: max((e.tier for e in es), key=lambda t: TIER_ORDER[t]) for g, es in groups.items()}

    official = [e for e in items if e.tier == "OFFICIAL" and not e.has_rumor_markers]
    if official and open_key_conflicts == 0:
        factors.append(ReliabilityFactorItem(F.OFFICIAL_CONFIRMED, f"groups={official[0].group}"))
        return done(Reliability.HIGH)

    rumor_groups = [g for g, es in groups.items() if all(e.has_rumor_markers for e in es)]
    if len(rumor_groups) / len(groups) >= 0.5:
        level = Reliability.LOW
        factors.append(
            ReliabilityFactorItem(F.RUMOR_MARKERS, f"groups={','.join(sorted(rumor_groups))}")
        )
    else:
        known = {g: t for g, t in best.items() if t is not None}
        top = sorted(g for g, t in known.items() if t in {"OFFICIAL", "A"})
        bees = sorted(g for g, t in known.items() if t == "B")
        if not known:
            level = Reliability.UNKNOWN
            factors.append(ReliabilityFactorItem(F.UNKNOWN_TIER))
        elif len(top) >= 2:
            level = Reliability.HIGH
            factors.append(
                ReliabilityFactorItem(F.INDEPENDENT_TIER_A_2PLUS, f"groups={','.join(top)}")
            )
        elif len(top) == 1:
            level = Reliability.MEDIUM
            factors.append(ReliabilityFactorItem(F.SINGLE_TIER_A, f"groups={top[0]}"))
        elif len(bees) >= 2:
            level = Reliability.MEDIUM
            factors.append(
                ReliabilityFactorItem(F.INDEPENDENT_TIER_B_2PLUS, f"groups={','.join(bees)}")
            )
        elif all(t == "C" for t in known.values()):
            level = Reliability.LOW
            factors.append(ReliabilityFactorItem(F.TIER_C_ONLY))
        else:
            level = Reliability.LOW
            factors.append(
                ReliabilityFactorItem(F.SINGLE_SOURCE, f"groups={','.join(sorted(known))}")
            )

    if all(e.clickbait for e in items) and level in DOWN:
        level = DOWN[level]
        factors.append(ReliabilityFactorItem(F.CLICKBAIT))
    if open_key_conflicts > 0 and level == Reliability.HIGH:
        level = Reliability.MEDIUM
        factors.append(
            ReliabilityFactorItem(F.OPEN_CONFLICT_CAP, f"conflicts={open_key_conflicts}")
        )
    return done(level)
