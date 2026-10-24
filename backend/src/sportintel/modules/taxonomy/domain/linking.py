"""Выбор сущности среди кандидатов (BE-T2.2 §7.3): чистая детерминированная логика."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    entity_id: uuid.UUID
    kind: str
    sport_id: str | None
    priority: int
    similarity: float
    matched_alias_norm: str


def choose(
    candidates: list[Candidate], context_entity_ids: set[uuid.UUID], sport_id: str | None = None
) -> Candidate | None:
    """Совпадающий спорт → больший priority → в контексте статьи → меньший id."""
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (
            0 if sport_id is not None and c.sport_id == sport_id else 1,
            -c.priority,
            0 if c.entity_id in context_entity_ids else 1,
            str(c.entity_id),
        ),
    )


def is_ambiguous(candidates: list[Candidate], chosen: Candidate, sport_id: str | None) -> bool:
    """Однофамильцы: ≥ 2 кандидата неразличимы по спорту и priority (BE-T2.2 §12)."""
    same = [
        c
        for c in candidates
        if c.priority == chosen.priority
        and (c.sport_id == sport_id) == (chosen.sport_id == sport_id)
    ]
    return len(same) > 1
