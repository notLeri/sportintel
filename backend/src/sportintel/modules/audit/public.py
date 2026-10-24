"""Публичный фасад аудита (BE-T3.1). Запись — в транзакции действия: откат действия откатывает и аудит."""

import uuid
from collections.abc import Mapping
from typing import Any

from sportintel.modules.audit.application import record as _record
from sportintel.modules.audit.domain.actions import AuditAction
from sportintel.modules.audit.domain.diff import diff
from sportintel.modules.audit.infrastructure.repository import SqlAuditStore
from sportintel.platform.db import UnitOfWork

__all__ = ["AuditAction", "diff", "list_entries", "record"]


async def record(
    uow: UnitOfWork,
    *,
    actor_id: uuid.UUID | None,
    action: AuditAction,
    target_type: str,
    target_id: str,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason: str | None = None,
    context_event_id: uuid.UUID | None = None,
) -> None:
    await _record.record(
        SqlAuditStore(uow.session),
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
        reason=reason,
        context_event_id=context_event_id,
    )


async def list_entries(
    uow: UnitOfWork,
    *,
    context_event_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    after: tuple[Any, int] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await SqlAuditStore(uow.session).list(
        context_event_id=context_event_id,
        target_type=target_type,
        target_id=target_id,
        after=after,
        limit=limit,
    )
