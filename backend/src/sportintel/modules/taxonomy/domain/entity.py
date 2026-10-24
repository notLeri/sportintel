import uuid
from dataclasses import dataclass, field
from typing import Any

from sportintel.modules.taxonomy.domain.values import EntityKind, EntityReviewState


@dataclass
class Entity:
    id: uuid.UUID
    kind: EntityKind
    sport_id: str | None
    canonical_name: str
    name_norm: str
    country: str | None = None
    external_ids: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    auto_created: bool = False
    review_state: EntityReviewState = EntityReviewState.APPROVED
    active: bool = True
    aliases: list[str] = field(default_factory=list)
