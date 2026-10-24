"""Команды источников (BE-T1.2). Аудит подключается в BE-T3.1."""

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol

from sportintel.modules.sources.domain.source import Source, normalize_domain
from sportintel.modules.sources.domain.values import SourceKind
from sportintel.platform.errors import ConcurrencyConflict, FieldError, NotFound, ValidationFailed
from sportintel.platform.ids import new_id

NULLABLE = {"tier", "owner_group"}


class SourceWriter(Protocol):
    async def get(self, source_id: uuid.UUID) -> Source | None: ...
    async def add(self, source: Source) -> None: ...
    async def update(self, source: Source, expected_version: int, now: datetime) -> Source: ...


async def create_source(
    store: SourceWriter,
    data: dict[str, Any],
    now: datetime,
    known_profiles: frozenset[str] = frozenset({"default"}),
) -> Source:
    source = Source(
        id=new_id(), domain=normalize_domain(data["base_url"]), next_poll_at=now, **data
    )
    source.validate(known_profiles)
    await store.add(source)
    return source


async def update_source(
    store: SourceWriter,
    source_id: uuid.UUID,
    patch: dict[str, Any],
    expected_version: int,
    now: datetime,
    known_profiles: frozenset[str] = frozenset({"default"}),
) -> Source:
    """`patch` — только переданные поля (model_fields_set). Смена kind и домена запрещена."""
    current = await store.get(source_id)
    if current is None:
        raise NotFound(f"source {source_id} not found")
    if current.version != expected_version:
        raise ConcurrencyConflict(current=None)  # роутер подставит актуальное представление
    if "kind" in patch:
        raise ValidationFailed(details=[FieldError("kind", "immutable", "kind cannot be changed")])
    for name, value in patch.items():
        if value is None and name not in NULLABLE:
            raise ValidationFailed(details=[FieldError(name, "required", f"{name} cannot be null")])
    if "base_url" in patch and normalize_domain(patch["base_url"]) != current.domain:
        raise ValidationFailed(
            details=[
                FieldError("base_url", "domain_change_forbidden", "a new domain is a new source")
            ]
        )

    updated = replace(current, **patch)
    if "poll_interval_seconds" in patch and current.next_poll_at is not None:
        soonest = now.timestamp() + updated.poll_interval_seconds
        if current.next_poll_at.timestamp() > soonest:
            updated.next_poll_at = datetime.fromtimestamp(soonest, tz=now.tzinfo)
    if patch.get("active") is True and not current.active:
        updated.next_poll_at = now
        updated.consecutive_failures = 0
    if updated.kind == SourceKind.MANUAL:
        updated.feed_urls = []
    updated.validate(known_profiles)
    return await store.update(updated, expected_version, now)
