"""Ручная оценка relevance/reliability (BE-T4.5)."""

import uuid
from collections.abc import Callable
from typing import Any, Literal

from sportintel.modules.audit import public as audit
from sportintel.modules.events.domain.actor import Actor
from sportintel.modules.events.domain.values import OverrideField, Relevance, Reliability, Role
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import ConcurrencyConflict, FieldError, NotFound, ValidationFailed

RepoFor = Callable[[UnitOfWork], Any]


async def override_assessment(
    uow: UnitOfWork,
    repo_for: RepoFor,
    event_id: uuid.UUID,
    kind: Literal["relevance", "reliability"],
    level: str | None,
    reason: str | None,
    actor_id: uuid.UUID,
    role: str,
    expected_version: int,
    clock: Clock,
) -> None:
    repo = repo_for(uow)
    e = await repo.get(event_id, for_update=True)
    if e is None:
        raise NotFound(f"event {event_id} not found")
    if e.version != expected_version:
        raise ConcurrencyConflict(current=None)
    now, actor = clock.now(), Actor(actor_id, Role(role))
    before = {"level": getattr(e, kind).level, "origin": getattr(e, kind).origin}
    if level is None:
        e.clear_override(OverrideField(kind), now)  # refresh вернёт расчётное значение
    else:
        enum = Relevance if kind == "relevance" else Reliability
        try:
            value = enum(level)
        except ValueError:
            raise ValidationFailed(
                details=[FieldError("level", "invalid", f"unknown level {level}")]
            ) from None
        (e.override_relevance if kind == "relevance" else e.override_reliability)(
            value, reason or "", actor, now
        )
    await repo.save(e, expected_version)
    action = (
        audit.AuditAction.EVENT_RELEVANCE_OVERRIDDEN
        if kind == "relevance"
        else audit.AuditAction.EVENT_RELIABILITY_OVERRIDDEN
    )
    await audit.record(
        uow,
        actor_id=actor_id,
        action=action,
        target_type="event",
        target_id=str(event_id),
        before=before,
        after={"level": level},
        reason=reason,
        context_event_id=event_id,
    )
