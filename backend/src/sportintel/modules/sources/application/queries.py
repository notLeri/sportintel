import uuid
from collections.abc import Collection
from typing import Protocol

from sportintel.modules.sources.application.dto import SourceMeta
from sportintel.modules.sources.domain.source import Source, normalize_domain
from sportintel.modules.sources.domain.values import SourceKind
from sportintel.platform.errors import NotFound
from sportintel.platform.ids import new_id


class SourceStore(Protocol):
    async def get(self, source_id: uuid.UUID) -> Source | None: ...
    async def get_many(self, ids: Collection[uuid.UUID]) -> list[Source]: ...
    async def get_by_domain(self, domain: str) -> Source | None: ...
    async def add_if_absent(self, source: Source) -> Source: ...


async def get_source_meta(store: SourceStore, source_id: uuid.UUID) -> SourceMeta:
    source = await store.get(source_id)
    if source is None:
        raise NotFound(f"source {source_id} not found")
    return SourceMeta.of(source)


async def get_sources_meta(
    store: SourceStore, ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, SourceMeta]:
    return {s.id: SourceMeta.of(s) for s in await store.get_many(ids)}


async def find_by_domain(store: SourceStore, domain: str) -> SourceMeta | None:
    source = await store.get_by_domain(normalize_domain(domain))
    return SourceMeta.of(source) if source else None


async def ensure_manual_source(store: SourceStore, domain: str) -> SourceMeta:
    """Источник для вручную добавленного URL: создаётся при первом обращении (BE-T1.10)."""
    domain = normalize_domain(domain)
    source = Source(
        id=new_id(),
        name=domain,
        domain=domain,
        base_url=f"https://{domain}",
        kind=SourceKind.MANUAL,
        tier=None,
        active=True,
    )
    source.validate()
    return SourceMeta.of(await store.add_if_absent(source))
