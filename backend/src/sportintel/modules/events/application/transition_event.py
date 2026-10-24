"""Переход статуса события пользователем (BE-T3.2)."""

import uuid
from collections.abc import Callable
from typing import Any

from sportintel.modules.audit import public as audit
from sportintel.modules.events.domain.actor import SYSTEM, Actor
from sportintel.modules.events.domain.policies.workflow import SYSTEM_ALLOWED, WorkflowPolicy
from sportintel.modules.events.domain.values import EventStatus, RejectionReason, Role
from sportintel.platform import flags
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import ConcurrencyConflict, FieldError, NotFound, ValidationFailed

RepoFor = Callable[[UnitOfWork], Any]


async def transition_event(
    uow: UnitOfWork,
    repo_for: RepoFor,
    event_id: uuid.UUID,
    to: EventStatus,
    actor_id: uuid.UUID,
    role: str,
    expected_version: int,
    reason: RejectionReason | None,
    comment: str | None,
    clock: Clock,
) -> None:
    if reason is not None and to != EventStatus.REJECTED:
        raise ValidationFailed(
            details=[FieldError("reason", "not_allowed", "reason only for REJECTED")]
        )
    repo = repo_for(uow)
    event = await repo.get(event_id, for_update=True)
    if event is None:
        raise NotFound(f"event {event_id} not found")
    if event.version != expected_version:
        raise ConcurrencyConflict(current=None)
    old = event.status
    event.transition(
        to,
        Actor(actor_id, Role(role)),
        clock.now(),
        reason=reason,
        comment=comment,
        draft_ready=event.draft_state == "ready",
        last_draft_author_id=event.draft_last_human_author_id,
        require_second_reviewer=flags.is_enabled("REQUIRE_SECOND_REVIEWER"),
    )
    await repo.save(event, expected_version)
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.EVENT_TRANSITIONED,
        target_type="event",
        target_id=str(event_id),
        before={"status": old},
        after={
            "status": event.status,
            "rejection_reason": event.rejection_reason,
            "rejection_comment": event.rejection_comment,
        },
        reason=comment,
        context_event_id=event_id,
    )


async def system_transition(
    uow: UnitOfWork, repo_for: RepoFor, event_id: uuid.UUID, to: EventStatus, clock: Clock
) -> bool:
    """Только SYSTEM_ALLOWED; False, если исходный статус не подходит (например, черновик сохранён в NEW)."""
    repo = repo_for(uow)
    event = await repo.get(event_id, for_update=True)
    if event is None or (event.status, to) not in SYSTEM_ALLOWED:
        return False
    event.transition(to, SYSTEM, clock.now(), draft_ready=True)
    await repo.save(event, event.version)
    return True


async def set_draft_status(
    uow: UnitOfWork,
    repo_for: RepoFor,
    event_id: uuid.UUID,
    draft_state: str,
    last_human_author_id: uuid.UUID | None,
) -> None:
    repo = repo_for(uow)
    event = await repo.get(event_id, for_update=True)
    if event is None:
        raise NotFound(f"event {event_id} not found")
    event.draft_state, event.draft_last_human_author_id = draft_state, last_human_author_id
    await repo.save(event, event.version)


def allowed_transitions_for(role: str) -> dict[str, list[dict[str, str]]]:
    return {
        str(frm): [{"to": str(to), "min_role": str(r)} for to, r in opts]
        for frm, opts in WorkflowPolicy.allowed_for(Role(role)).items()
    }
