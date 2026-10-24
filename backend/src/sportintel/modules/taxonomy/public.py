"""Публичный фасад модуля taxonomy."""

import time
import uuid
from collections.abc import Collection
from dataclasses import dataclass, field

from sportintel.modules.taxonomy.application import linking as _linking
from sportintel.modules.taxonomy.application.linking import FoundEntity, LinkResult, Mention
from sportintel.modules.taxonomy.domain.values import EntityKind, EntityReviewState
from sportintel.modules.taxonomy.infrastructure.repository import (
    SqlLinkStore,
    SqlTaxonomyRepository,
    entity_dto_row,
)
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.text import normalize_name

__all__ = [
    "EntityDTO",
    "EntityKind",
    "SportDTO",
    "admin_router",
    "competition_aliases_for_prompt",
    "display_by_name",
    "get_entities",
    "list_sports",
    "router",
    "search_entities",
]


@dataclass(frozen=True)
class SportDTO:
    id: str
    name_i18n: dict[str, str]
    sort: int
    active: bool


@dataclass(frozen=True)
class EntityDTO:
    id: uuid.UUID
    kind: EntityKind
    sport_id: str | None
    name: str  # canonical_name: как в источниках, по нему ищутся упоминания
    priority: int
    review_state: EntityReviewState
    name_i18n: dict[str, str] = field(default_factory=dict)

    def display(self, lang: str) -> str:
        """Название на языке интерфейса; нет перевода (клубы, имена) — как в источниках."""
        return self.name_i18n.get(lang) or self.name


async def list_sports(uow: UnitOfWork, active_only: bool = True) -> list[SportDTO]:
    return [
        SportDTO(**r) for r in await SqlTaxonomyRepository(uow.session).list_sports(active_only)
    ]


async def get_entities(uow: UnitOfWork, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, EntityDTO]:
    rows = await SqlTaxonomyRepository(uow.session).get_many(ids)
    return {r["id"]: EntityDTO(**entity_dto_row(r)) for r in rows}


_prompt_cache: list[tuple[float, list[tuple[str, list[str], str]]]] = []


async def competition_aliases_for_prompt(uow: UnitOfWork) -> list[tuple[str, list[str], str]]:
    """Для префикса LLM-промпта (фаза L). Кэш процесса 10 мин."""
    if _prompt_cache and _prompt_cache[0][0] > time.monotonic():
        return _prompt_cache[0][1]
    value = await SqlTaxonomyRepository(uow.session).competition_aliases()
    _prompt_cache[:] = [(time.monotonic() + 600, value)]
    return value


async def link_entities(
    uow: UnitOfWork,
    mentions: list[Mention],
    clock: Clock,
    sample_article_id: uuid.UUID | None = None,
) -> list[LinkResult]:
    return await _linking.link_entities(
        SqlLinkStore(uow.session), mentions, clock.now(), sample_article_id
    )


async def find_mentions(
    uow: UnitOfWork, text: str, sport_id: str | None = None
) -> list[FoundEntity]:
    return await _linking.find_mentions(SqlLinkStore(uow.session), text, sport_id)


async def search_entities(
    uow: UnitOfWork,
    query: str,
    limit: int = 5,
    threshold: float = 0.5,
    kind: str | None = None,
    sport: str | None = None,
    prefix: bool = False,
) -> list[uuid.UUID]:
    """Поиск сущностей по алиасам (BE-T2.22, BE-T2.24); query нормализуется здесь."""
    found = await SqlTaxonomyRepository(uow.session).search(
        normalize_name(query), limit, threshold, kind, sport, prefix
    )
    return [i for i, _ in found]


from sportintel.modules.taxonomy.api.admin_router import router as admin_router  # noqa: E402
from sportintel.modules.taxonomy.api.router import router  # noqa: E402


async def display_by_name(uow: UnitOfWork, names: Collection[str], lang: str) -> dict[str, str]:
    """canonical_name турнира → название на языке интерфейса (для обоснований важности)."""
    from sqlalchemy import text

    if not names:
        return {}
    rows = await uow.session.execute(
        text(
            "SELECT canonical_name, name_i18n->>:l FROM taxonomy.entities"
            " WHERE canonical_name = ANY(:n) AND name_i18n ? :l"
        ),
        {"n": list(names), "l": lang},
    )
    return {r[0]: r[1] for r in rows if r[1]}
