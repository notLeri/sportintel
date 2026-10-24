"""Результат обогащения — одинаковый для правил и LM (BE-T2.7 §7, ADR-004)."""

import uuid
from dataclasses import dataclass, field
from datetime import date

from sportintel.modules.intelligence.domain.values import ClaimAttribute, ClaimModality, Relevance


@dataclass(frozen=True)
class EntityMention:
    mention: str
    kind: str
    role: str  # subject | mentioned
    canonical_guess: str | None = None
    entity_id: uuid.UUID | None = None  # уже связано (поиск алиасов в режиме rules)


@dataclass(frozen=True)
class Claim:
    subject: str
    attribute: ClaimAttribute
    value: str
    modality: ClaimModality
    quote: str


@dataclass(frozen=True)
class RelevanceOut:
    level: Relevance
    rationale: str


@dataclass(frozen=True)
class EnrichOutput:
    language: str
    is_sports: bool
    sport: str | None
    competition: EntityMention | None
    entities: list[EntityMention]
    claims: list[Claim]
    rumor_markers: list[str]
    clickbait: bool
    event_date_hint: date | None
    headline_neutral: str
    relevance: RelevanceOut
    method: str = "rules"
    applied_rules: list[str] = field(default_factory=list)
